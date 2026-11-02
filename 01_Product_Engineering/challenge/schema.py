import json
import logging
import os
from collections import Counter
from pathlib import Path
from uuid import uuid4

import gradio as gr
from pydantic import BaseModel, Field

from config import config_from_env
from extraction.adapters import adapter_for
from extraction.context import plan_work_units
from extraction.parse import parse_document
from llm import _artifact_prompt_text, extract_tax_fields, run_extraction_stage, extract_tax_info
from schemas.api.extraction import (
    BundleExtraction,
    ExtractionIssue,
    FormResult,
    TaxFact,
)
from schemas.audit.audit import (
    AuditFinding,
    AuditResult,
    FindingSeverity,
    FindingType,
)
from schemas.common.enum import (
    ObservationStatus,
    ReviewStatus,
    TaxDocumentType,
)
from schemas.domain.forms.factory import (
    create_form_definition,
    identify_artifact_form,
    require_readable_fields,
)
from schemas.domain.tax_document import TaxDocument, TaxEvidence, TaxFormField
from schemas.extraction.extraction import ExtractionArtifact
from schemas.domain.bundle import BundleForm
from schemas.domain.tax_document import (
    BundleLinksDraft,
    FactDraft,
    FactSource,
    FormDiscoveryDraft,
    FormExtractionDraft,
    ProcessedBundle,
    ProcessedFact,
    ProcessedForm,
)

logger = logging.getLogger(__name__)

BIFROST_CONFIG = config_from_env()


class Request(BaseModel):
    """Files submitted through the UI."""

    files: list[gr.FileData] = Field(
        min_length=1,
        max_length=1,
        description="One uploaded tax document",
    )


Response = BundleExtraction


def solve(req: Request) -> Response:
    parsed_files = parse_document(req.files, BIFROST_CONFIG.parser)
    if len(parsed_files) != 1:
        raise ValueError("This extractor accepts one PDF package at a time")

    md_text = adapter_for(BIFROST_CONFIG.parser).to_markdown(parsed_files[0])
    prompt = f"""Find all known facts about the partnership (the company), the partner (the human being), and all their taxable information across all document pages and tax forms.
    DOCUMENT TEXT:\n\n{md_text}
    """
    result = extract_tax_info(prompt, BundleExtraction)
    print("LLM response:\n")
    print(result)
    return BundleExtraction()

# def solve(req: Request) -> Response:
#     """Extract every discovered form and source-native fact from one PDF package."""
    # parsed_files = parse_document(req.files, BIFROST_CONFIG.parser)
#     if len(parsed_files) != 1:
#         raise ValueError("This extractor accepts one PDF package at a time")
#
#     artifact = adapter_for(BIFROST_CONFIG.parser).adapt(parsed_files[0])
#     logger.info(
#         "Parsed %s with %s: %d pages, %d elements, %d warnings",
#         artifact.source_document.filename,
#         artifact.parser.value,
#         len(artifact.pages),
#         sum(len(page.elements) for page in artifact.pages),
#         len(artifact.warnings),
#     )
#     return response_from_bundle(process_bundle(artifact))


def _checkpoint_path(artifact: ExtractionArtifact, name: str) -> Path:
    return (
        Path(os.getenv("EXTRACTION_CHECKPOINT_DIR", ".extraction-checkpoints"))
        / artifact.source_document.id
        / f"{name}.json"
    )


def _run_stage(
    artifact: ExtractionArtifact,
    stage: str,
    payload: dict,
    response_model: type[BaseModel],
    checkpoint_name: str,
    page_numbers: list[int] | None,
) -> BaseModel:
    checkpoint = _checkpoint_path(artifact, checkpoint_name)
    if checkpoint.exists():
        return response_model.model_validate_json(
            json.loads(checkpoint.read_text())["raw_response"]
        )
    selected_pages = page_numbers or [page.page_number for page in artifact.pages]
    extra_rules = payload.get("rules", [])
    prompt = {
        "stage": stage,
        "document_sha256": artifact.source_document.sha256,
        "page_numbers": selected_pages,
        "evidence": _artifact_prompt_text(artifact, selected_pages),
        "rules": [
            "Cite only evidence element IDs shown in this request.",
            "Preserve every source-native printed label, locator/code, and raw value.",
            "Do not infer a missing value as zero; use only response_schema observation statuses and finding types.",
            *extra_rules,
        ],
        **{key: value for key, value in payload.items() if key != "rules"},
    }
    raw: list[str] = []
    result = run_extraction_stage(prompt, response_model, raw.append)
    if not raw:
        raise ValueError(f"{stage} completed without a raw response")
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_text(
        json.dumps({"request": {"messages": prompt}, "raw_response": raw[0]})
    )
    return result


def _source_map(artifact: ExtractionArtifact) -> dict[str, object]:
    return {element.id: element for page in artifact.pages for element in page.elements}


def _tax_fact(draft: FactDraft, occurrence: int) -> TaxFact:
    qualifiers = dict(draft.qualifiers)
    if occurrence > 1:
        qualifiers["occurrence"] = str(occurrence)
    return TaxFact(
        field_id=draft.field_id,
        observation_status=draft.observation_status,
        value=draft.value,
        code=draft.code,
        qualifiers=qualifiers or None,
        status=ReviewStatus.EXTRACTED,
    )


def _discovery_for_work_units(
    artifact: ExtractionArtifact,
) -> tuple[list[FormDiscoveryDraft], list[ExtractionIssue]]:
    """Discover bounded page groups while keeping every page owned exactly once."""
    discoveries = []
    issues = []
    for unit in plan_work_units(artifact):
        prompt_pages = list(unit.owned_page_numbers + unit.context_page_numbers)
        draft = _run_stage(
            artifact,
            "discover",
            {
                "owned_page_numbers": list(unit.owned_page_numbers),
                "rules": [
                    "Only assign pages in owned_page_numbers to forms.",
                    "The remaining supplied pages are context only and must not be assigned.",
                    "For K-1 pages, use a stable package ID: federal-k1, "
                    "federal-k1-supporting-schedules, or <state>-k1; use a descriptive "
                    "kebab-case ID for letters and tables of contents.",
                ],
            },
            FormDiscoveryDraft,
            f"discover-pages-{'-'.join(map(str, unit.owned_page_numbers))}",
            prompt_pages,
        )
        owned = set(unit.owned_page_numbers)
        forms = []
        for form in draft.forms:
            pages = [page for page in form.page_numbers if page in owned]
            if not pages:
                continue
            forms.append(form.model_copy(update={"page_numbers": pages}))
        discoveries.append(FormDiscoveryDraft(forms=forms, issues=draft.issues))
    return discoveries, issues


def _merge_discovered_forms(drafts: list[FormDiscoveryDraft]) -> list[BundleForm]:
    """Rejoin a form that crosses bounded discovery work units."""
    forms: dict[str, BundleForm] = {}
    for draft in drafts:
        for discovered in draft.forms:
            form = BundleForm.model_validate(discovered)
            previous = forms.get(form.id)
            if previous is None:
                forms[form.id] = form
                continue
            if previous.model_dump(exclude={"page_numbers"}) == form.model_dump(
                exclude={"page_numbers"}
            ):
                forms[form.id] = previous.model_copy(
                    update={"page_numbers": previous.page_numbers + form.page_numbers}
                )
                continue
            # Models commonly restart generated identifiers in each bounded
            # discovery call. Keep distinct identities rather than dropping a
            # later form or aborting the package.
            renamed_id = f"{form.id}-page-{form.page_numbers[0]}"
            while renamed_id in forms:
                renamed_id = f"{renamed_id}-next"
            forms[renamed_id] = form.model_copy(update={"id": renamed_id})
    return list(forms.values())


def process_bundle(artifact: ExtractionArtifact) -> ProcessedBundle:
    """Discover and extract all pages, retaining only evidence owned by each form."""
    elements = _source_map(artifact)
    if not any(element.text for element in elements.values()):
        return ProcessedBundle(
            issues=[
                ExtractionIssue(
                    finding_type=FindingType.MISSING_EVIDENCE,
                    severity=FindingSeverity.ERROR,
                    message="No readable source elements were produced by the parser",
                )
            ]
        )
    work_units = plan_work_units(artifact)

    discovery_drafts, issues = _discovery_for_work_units(artifact)
    forms = _merge_discovered_forms(discovery_drafts)
    issues.extend(issue for draft in discovery_drafts for issue in draft.issues)
    assigned = {page for form in forms for page in form.page_numbers}
    for page in artifact.pages:
        if page.page_number not in assigned:
            identifier = f"unknown-page-{page.page_number}"
            forms.append(
                BundleForm(
                    id=identifier,
                    document_type=TaxDocumentType.UNKNOWN,
                    page_numbers=[page.page_number],
                )
            )
            issues.append(
                ExtractionIssue(
                    finding_type=FindingType.OTHER,
                    severity=FindingSeverity.WARNING,
                    message=f"Page {page.page_number} was not assigned by discovery",
                    form_id=identifier,
                )
            )
    processed_forms = []
    for form in forms:
        extracted_drafts = [
            _run_stage(
                artifact,
                "extract",
                {
                    "form": form.model_dump(mode="json"),
                    "rules": [
                        "Extract every printed field and table row, including explicit blanks and zeroes.",
                        "Use canonical snake_case field IDs. Use entity.ein, entity.name, entity.address, "
                        "partner.taxpayer_id, partner.name, partner.address, partner.ownership_percentage, "
                        "partner.liabilities, and partner.capital_* for shared K-1 fields.",
                        "For federal boxes use federal.<normalized_box_label>; for state fields use "
                        "<lowercase_jurisdiction>.<normalized_printed_label>. Retain the printed label in locator.label.",
                        "Use qualifiers for repeated table dimensions such as box, code, line, column, period, "
                        "share_type, source, activity, or business; never encode those dimensions in field_id.",
                    ],
                },
                FormExtractionDraft,
                f"extract-{form.id}-page-{page}",
                [page],
            )
            for page in form.page_numbers
        ]
        extracted = FormExtractionDraft(
            facts=[fact for draft in extracted_drafts for fact in draft.facts],
            issues=[issue for draft in extracted_drafts for issue in draft.issues],
        )
        processed, fingerprints = [], {}
        for draft in extracted.facts:
            owned = [
                elements[item]
                for item in draft.evidence_element_ids
                if item in elements
                and any(
                    location.page in form.page_numbers
                    for location in elements[item].locations
                )
            ]
            foreign = set(draft.evidence_element_ids) - {item.id for item in owned}
            sources = [
                FactSource(
                    element_id=item.id,
                    locations=item.locations,
                    text=item.text or "",
                    locator=draft.locator,
                )
                for item in owned
            ]
            key = (
                draft.field_id,
                draft.code,
                tuple(sorted(draft.qualifiers.items())),
                draft.value and draft.value.model_dump_json(),
            )
            if key in fingerprints:
                fingerprints[key].sources.extend(sources)
                fingerprints[key].fact.status = ReviewStatus.NEEDS_REVIEW
                continue
            occurrence = 1 + sum(
                item.fact.field_id == draft.field_id and item.fact.code == draft.code
                for item in processed
            )
            conflicting = any(
                item.fact.field_id == draft.field_id
                and item.fact.code == draft.code
                and (item.fact.qualifiers or {}) == (draft.qualifiers or {})
                and item.fact.value != draft.value
                for item in processed
            )
            fact = ProcessedFact(
                id=draft.id
                if all(item.id != draft.id for item in processed)
                else f"{draft.id}-{occurrence}",
                fact=_tax_fact(draft, occurrence),
                description=draft.description,
                sources=sources,
            )
            if conflicting:
                issues.append(
                    ExtractionIssue(
                        finding_type=FindingType.CONFLICTING_VALUES,
                        severity=FindingSeverity.WARNING,
                        message=f"Conflicting source-native values for {draft.field_id}",
                        form_id=form.id,
                        field_id=draft.field_id,
                    )
                )
            if foreign:
                fact.fact.status = ReviewStatus.NEEDS_REVIEW
                issues.append(
                    ExtractionIssue(
                        finding_type=FindingType.MISSING_EVIDENCE,
                        severity=FindingSeverity.WARNING,
                        message=f"Fact {draft.id} cited evidence outside its owned pages",
                        form_id=form.id,
                        field_id=draft.field_id,
                    )
                )
            fingerprints[key] = fact
            processed.append(fact)
        issues.extend(extracted.issues)
        processed_forms.append(
            ProcessedForm(form=BundleForm.model_validate(form), facts=processed)
        )
    link_drafts = [
        _run_stage(
            artifact,
            "link",
            {"owned_page_numbers": list(unit.owned_page_numbers)},
            BundleLinksDraft,
            f"link-pages-{'-'.join(map(str, unit.owned_page_numbers))}",
            list(unit.owned_page_numbers + unit.context_page_numbers),
        )
        for unit in work_units
    ]
    known_facts = {
        (form.form.id, fact.id) for form in processed_forms for fact in form.facts
    }
    relationships = []
    for draft in link_drafts:
        for relationship in draft.relationships:
            if (
                (relationship.source.form_id, relationship.source.fact_id)
                and (relationship.target.form_id, relationship.target.fact_id)
                and (relationship.source.form_id, relationship.source.fact_id)
                in known_facts
                and (relationship.target.form_id, relationship.target.fact_id)
                in known_facts
            ):
                relationships.append(relationship)
                continue
            issues.append(
                ExtractionIssue(
                    finding_type=FindingType.MISSING_EVIDENCE,
                    severity=FindingSeverity.WARNING,
                    message="Linking result referenced an unknown extracted fact",
                )
            )
    return ProcessedBundle(
        forms=processed_forms, issues=issues, relationships=relationships
    )


def response_from_bundle(bundle: ProcessedBundle) -> BundleExtraction:
    return BundleExtraction(
        forms=[
            FormResult(
                **form.form.model_dump(), facts=[fact.fact for fact in form.facts]
            )
            for form in bundle.forms
        ],
        issues=bundle.issues,
    )
