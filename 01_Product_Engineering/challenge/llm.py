"""The model call.

One function, one job: take a conversation, stream back the assistant's reply.

Everything provider-specific lives in environment variables, so switching from
OpenAI to Azure to a self-hosted model is a config change, not a code change.
That property matters more than it looks like it does right now -- see the
"Where does this live?" section of the README.
"""

import json
import os

from litellm import completion
from pydantic import BaseModel

from schemas.domain.forms.form_definition import FormDefinition
from schemas.domain.tax_document import TaxExtractionDraft
from schemas.extraction.extraction import ExtractionArtifact

# LiteLLM picks the provider from the model string:
#   "gpt-4.1-mini"                    -> OpenAI
#   "azure/my-deployment"             -> Azure OpenAI
#   "anthropic/claude-sonnet-5"       -> Anthropic
#   "ollama/llama3.2"                 -> a model running on your laptop
#   "openai/my-model" + LLM_API_BASE  -> any OpenAI-compatible server (vLLM, LM Studio, ...)
MODEL = os.getenv("LLM_MODEL", "gpt-4.1-mini")
API_BASE = os.getenv("LLM_API_BASE")  # only needed for self-hosted / gateway endpoints
EXTRA_HEADERS = json.loads(os.getenv("LLM_EXTRA_HEADERS") or "{}")

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are a helpful assistant. Be concise and concrete.",
)


def stream_reply(message: str, history: list[dict] | None = None):
    """Yield the assistant's reply as it arrives, one growing string at a time.

    `history` is a list of {"role": ..., "content": ...} dicts. We rebuild the
    full message list on every turn -- the model is stateless, so the
    conversation only exists because we keep sending it.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": message})

    kwargs = {"model": MODEL, "messages": messages, "stream": True}
    if API_BASE:
        kwargs["api_base"] = API_BASE
    if EXTRA_HEADERS:
        kwargs["extra_headers"] = EXTRA_HEADERS

    reply = ""
    for chunk in completion(**kwargs):
        piece = chunk.choices[0].delta.content
        if piece:
            reply += piece
            yield reply


def extract_tax_fields(
    artifact: ExtractionArtifact,
    definition: FormDefinition,
    page_numbers: list[int] | None = None,
) -> TaxExtractionDraft:
    """Make one structured model call to map parser evidence to defined fields."""
    elements = [
        {
            "id": element.id,
            "text": element.text,
            "label": element.extractor_label,
            "locations": [
                {
                    "page": location.page,
                    "bbox": location.bbox.model_dump(mode="json") if location.bbox else None,
                }
                for location in element.locations
            ],
        }
        for page in artifact.pages
        if page_numbers is None or page.page_number in page_numbers
        for element in page.elements
        if element.text
    ]
    response_format: type[BaseModel] = TaxExtractionDraft
    prompt = {
        "task": "Extract the listed fields from this tax form.",
        "rules": [
            "Only return field IDs present in the supplied definition.",
            "Return one outcome for every defined field.",
            "Use not_found when no value evidence is extracted. Do not call a field blank just because its value is absent from text.",
            "Use unreadable only when the supplied evidence shows a present but illegible value; such results require human review.",
            "Never infer or calculate a value. Preserve negative signs and decimal values.",
            "For each outcome, cite evidence_element_ids from the supplied elements.",
            "Use the exact value kind from the field definition (money, text, percentage, boolean, count, or date).",
        ],
        "definition": definition.model_dump(mode="json"),
        "document": {
            "filename": artifact.source_document.filename,
            "page_numbers": page_numbers,
            "elements": elements,
        },
    }
    kwargs = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Return only the requested structured extraction."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "response_format": response_format,
        "stream": False,
    }
    if API_BASE:
        kwargs["api_base"] = API_BASE
    if EXTRA_HEADERS:
        kwargs["extra_headers"] = EXTRA_HEADERS

    result = completion(**kwargs)
    content = result.choices[0].message.content
    if not isinstance(content, str):
        raise ValueError("The extraction model returned no JSON content")
    return TaxExtractionDraft.model_validate_json(content)
