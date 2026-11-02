"""The model call.

One function, one job: take a conversation, stream back the assistant's reply.

Everything provider-specific lives in environment variables, so switching from
OpenAI to Azure to a self-hosted model is a config change, not a code change.
That property matters more than it looks like it does right now -- see the
"Where does this live?" section of the README.
"""
import base64

import json
import os
import threading
import time
from collections import deque
from collections.abc import Callable

from litellm import completion
from pydantic import BaseModel, ValidationError

from schemas.domain.forms.form_definition import FormDefinition
from schemas.domain.tax_document import TaxExtractionDraft
from schemas.extraction.extraction import ExtractionArtifact
from extraction.context import estimate_tokens

# LiteLLM picks the provider from the model string:
#   "gpt-4.1-mini"                    -> OpenAI
#   "azure/my-deployment"             -> Azure OpenAI
#   "anthropic/claude-sonnet-5"       -> Anthropic
#   "ollama/llama3.2"                 -> a model running on your laptop
#   "openai/my-model" + LLM_API_BASE  -> any OpenAI-compatible server (vLLM, LM Studio, ...)
MODEL = os.getenv("LLM_MODEL", "openai/qwen3.8-27b-mm")
API_BASE = os.getenv("LLM_API_BASE")  # only needed for self-hosted / gateway endpoints
EXTRA_HEADERS = json.loads(os.getenv("LLM_EXTRA_HEADERS") or "{}")

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "Return only valid JSON matching the requested structured extraction.",
)

def extract_tax_info(prompt: str, response_model: type[BaseModel] | None = None) -> str | None:
    print(f"Estimated tokens: {estimate_tokens(prompt)}")
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {"role": "user", "content": prompt},
    ]

    arg_dict = _completion_kwargs(messages, response_model)

    start = time.time()
    result = completion(**arg_dict)
    total_time = start - time.time()
    print(f"Processing time: {total_time}")
    content = result.choices[0].message.content
    if not isinstance(content, str):
        raise ValueError("The extraction model returned no content")
    return content



class _RateLimiter:
    """Process-local request and input-token limiter for the shared gateway."""

    def __init__(self) -> None:
        self._requests: deque[float] = deque()
        self._tokens: deque[tuple[float, int]] = deque()
        self._lock = threading.Lock()

    def wait(self, token_count: int) -> None:
        request_limit = int(os.getenv("LLM_REQUESTS_PER_MINUTE", "30"))
        token_limit = int(os.getenv("LLM_TOKENS_PER_MINUTE", "120000"))
        if request_limit < 1 or token_limit < 1:
            raise ValueError("LLM rate limits must be positive")
        if token_count > token_limit:
            raise ValueError("Prompt exceeds LLM_TOKENS_PER_MINUTE")
        while True:
            with self._lock:
                now = time.monotonic()
                cutoff = now - 60
                while self._requests and self._requests[0] <= cutoff:
                    self._requests.popleft()
                while self._tokens and self._tokens[0][0] <= cutoff:
                    self._tokens.popleft()
                used_tokens = sum(count for _, count in self._tokens)
                if (
                    len(self._requests) < request_limit
                    and used_tokens + token_count <= token_limit
                ):
                    self._requests.append(now)
                    self._tokens.append((now, token_count))
                    return
                waits = []
                if len(self._requests) >= request_limit:
                    waits.append(self._requests[0] + 60 - now)
                if used_tokens + token_count > token_limit:
                    required = used_tokens + token_count - token_limit
                    released = 0
                    for recorded_at, count in self._tokens:
                        released += count
                        if released >= required:
                            waits.append(recorded_at + 60 - now)
                            break
            time.sleep(max(0.01, min(waits)))


_RATE_LIMITER = _RateLimiter()


def _completion_kwargs(
    messages: list[dict], response_model: type[BaseModel] | None = None
) -> dict:
    # _RATE_LIMITER.wait(
    #     max(1, sum((len(message["content"]) + 3) // 4 for message in messages))
    # )
    kwargs = {"model": MODEL, "messages": messages, "stream": False}
    if response_model is not None:
        # The gateway rejects Pydantic's discriminated-union JSON Schema as an
        # OpenAI response_format. Keep JSON mode at the transport boundary and
        # validate the model's output against the full schema locally.
        kwargs["response_format"] = {"type": "json_object"}
    if API_BASE:
        kwargs["api_base"] = API_BASE
    if EXTRA_HEADERS:
        kwargs["extra_headers"] = EXTRA_HEADERS
    return kwargs


def stream_reply(message: str, history: list[dict] | None = None):
    """Yield the assistant's reply as it arrives, one growing string at a time.

    `history` is a list of {"role": ..., "content": ...} dicts. We rebuild the
    full message list on every turn -- the model is stateless, so the
    conversation only exists because we keep sending it.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": message})

    kwargs = _completion_kwargs(messages)
    kwargs["stream"] = True

    reply = ""
    for chunk in completion(**kwargs):
        piece = chunk.choices[0].delta.content
        if piece:
            reply += piece
            yield reply


def _artifact_prompt_text(
    artifact: ExtractionArtifact,
    page_numbers: list[int] | None,
) -> str:
    """Render parser elements as concise, citeable evidence lines for the model."""
    lines = []
    for page in artifact.pages:
        if page_numbers is not None and page.page_number not in page_numbers:
            continue
        for element in page.elements:
            if not element.text:
                continue
            lines.append(_evidence_line(element))
    return "\n".join(lines)


def _evidence_line(element) -> str:
    text = " ".join(element.text.split())
    locations = []
    for location in element.locations:
        if location.bbox:
            bbox = location.bbox
            locations.append(
                f"p{location.page} ({bbox.x0:.0f},{bbox.y0:.0f})-"
                f"({bbox.x1:.0f},{bbox.y1:.0f})"
            )
        else:
            locations.append(f"p{location.page}")
    label = f" {element.extractor_label}" if element.extractor_label else ""
    return f"[{element.id}] {'; '.join(locations)}{label} | {text}"


def _field_hints(
    artifact: ExtractionArtifact,
    definition: FormDefinition,
    page_numbers: list[int] | None,
) -> list[dict]:
    """Focus the model on each mapped label and the next local evidence lines."""
    elements = [
        element
        for page in artifact.pages
        if page_numbers is None or page.page_number in page_numbers
        for element in page.elements
        if element.text
    ]
    hints = []
    for field in definition.fields:
        labels = [" ".join(label.casefold().split()) for label in field.source.labels]
        matches = [
            index
            for index, element in enumerate(elements)
            if any(
                label in " ".join(element.text.casefold().split()) for label in labels
            )
        ]
        if not matches:
            continue
        evidence = []
        for index in matches:
            page = elements[index].locations[0].page
            for candidate in elements[index : index + 4]:
                if candidate.locations[0].page != page:
                    break
                line = _evidence_line(candidate)
                if line not in evidence:
                    evidence.append(line)
        hints.append({"field_id": field.id, "nearby_evidence": evidence})
    return hints


def build_extraction_prompt(
    artifact: ExtractionArtifact,
    definition: FormDefinition,
    page_numbers: list[int] | None = None,
) -> dict:
    """Build the structured-extraction prompt shared by production and inspection."""
    return {
        "task": "Extract the listed fields from this tax form.",
        "rules": [
            "Only return field IDs present in the supplied definition.",
            "Return one outcome for every defined field.",
            "Use not_found when no value evidence is extracted. Do not call a field blank just because its value is absent from text.",
            "Use unreadable only when the supplied evidence shows a present but illegible value; such results require human review.",
            "Never infer or calculate a value. Preserve negative signs and decimal values.",
            "For each outcome, cite evidence_element_ids using the ID in square brackets on an evidence line.",
            "Coordinates use a top-left origin: x increases rightward and y increases downward. Use nearby labels and values together.",
            "field_hints group each mapped label with its next evidence lines in reading order. If a hint contains a plausible adjacent value, return it as observed rather than not_found.",
            "Use the exact value kind from the field definition (money, text, percentage, boolean, count, or date).",
        ],
        "definition": definition.model_dump(mode="json"),
        "document": {
            "filename": artifact.source_document.filename,
            "page_numbers": page_numbers,
            "field_hints": _field_hints(artifact, definition, page_numbers),
            "evidence": _artifact_prompt_text(artifact, page_numbers),
        },
    }


def extraction_messages(prompt: dict) -> list[dict[str, str]]:
    """Return the exact messages sent to the structured extraction model."""
    return [
        {
            "role": "system",
            "content": "Return only valid JSON matching the requested structured extraction.",
        },
        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
    ]


def extract_tax_fields(
    artifact: ExtractionArtifact,
    definition: FormDefinition,
    page_numbers: list[int] | None = None,
    response_sink: Callable[[str], None] | None = None,
) -> TaxExtractionDraft:
    """Make one structured model call to map parser evidence to defined fields."""
    response_format: type[BaseModel] = TaxExtractionDraft
    prompt = build_extraction_prompt(artifact, definition, page_numbers)

    prompt["response_schema"] = response_format.model_json_schema()
    kwargs = _completion_kwargs(extraction_messages(prompt), response_format)

    result = completion(**kwargs)
    content = result.choices[0].message.content
    if not isinstance(content, str):
        raise ValueError("The extraction model returned no JSON content")
    if response_sink is not None:
        response_sink(content)
    return TaxExtractionDraft.model_validate_json(content)


def run_extraction_stage(
    prompt: dict,
    response_model: type[BaseModel],
    response_sink: Callable[[str], None] | None = None,
) -> BaseModel:
    """Run a bounded generic bundle stage with a strict response contract."""
    prompt = {**prompt, "response_schema": response_model.model_json_schema()}
    messages = extraction_messages(prompt)
    for attempt in range(2):
        result = completion(**_completion_kwargs(messages, response_model))
        content = result.choices[0].message.content
        if not isinstance(content, str):
            raise ValueError("The extraction model returned no JSON content")
        try:
            validated = response_model.model_validate_json(content)
        except ValidationError as exc:
            if attempt:
                raise ValueError(
                    f"The extraction model returned invalid {response_model.__name__} JSON"
                ) from exc
            messages.extend(
                [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            "Correct the JSON so it validates against response_schema. "
                            f"Validation errors: {exc}. Return only corrected JSON."
                        ),
                    },
                ]
            )
            continue
        if response_sink is not None:
            response_sink(content)
        return validated
    raise AssertionError("unreachable")
