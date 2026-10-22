import logging
from collections import Counter
from uuid import uuid4

import gradio as gr
from pydantic import BaseModel, Field

from config import config_from_env
from extraction.adapters import adapter_for
from extraction.parse import parse_document
from llm import extract_tax_fields
from schemas.audit.audit import (
    AuditFinding,
    AuditResult,
    FindingSeverity,
    FindingType,
)
from schemas.common.enum import (
    ObservationStatus,
    ReviewStatus,
)
from schemas.domain.forms.factory import (
    create_form_definition,
    identify_artifact_form,
    require_readable_fields,
)
from schemas.domain.tax_document import TaxDocument, TaxEvidence, TaxFormField
from schemas.extraction.extraction import ExtractionArtifact

logger = logging.getLogger(__name__)

BIFROST_CONFIG = config_from_env()

class Request(BaseModel):
    """Files submitted through the UI."""

    files: list[gr.FileData] = Field(
        min_length=1,
        max_length=1,
        description="One uploaded tax document",
    )

class Response(BaseModel):
    """Structured extraction and audit result for one uploaded PDF."""

    document: TaxDocument
    extraction_artifact: ExtractionArtifact
    audit_result: AuditResult

def solve(req: Request) -> Response:
    parsed_files = parse_document(BIFROST_CONFIG.parser, req.files)
    if len(parsed_files) != 1:
        raise ValueError("This MVP accepts one PDF at a time")

    artifact = adapter_for(BIFROST_CONFIG.parser).adapt(parsed_files[0])
    logger.info(
        "Parsed %s with %s: %d pages, %d elements, %d warnings",
        artifact.source_document.filename,
        artifact.parser.value,
        len(artifact.pages),
        sum(len(page.elements) for page in artifact.pages),
        len(artifact.warnings),
    )
    identity = identify_artifact_form(artifact)
    logger.info("Identified %s %s on pages %s", identity.return_type.value, identity.tax_year, identity.page_numbers)
    definition = create_form_definition(identity)
    page_numbers = identity.page_numbers
    if not page_numbers:
        raise ValueError("Could not identify the K-1 page in the PDF")
    require_readable_fields(artifact, definition, page_numbers)

    draft = extract_tax_fields(artifact, definition, page_numbers)
    logger.info("Model draft outcomes: %s", dict(Counter(field.observation_status.value for field in draft.fields)))
    if draft.form_id != definition.form_id or draft.tax_year != definition.tax_year:
        raise ValueError("The model's form identification does not match the selected definition")

    document_id = str(uuid4())
    expected = {field.id: field for field in definition.fields}
    elements = {
        element.id: element
        for page in artifact.pages
        if page.page_number in page_numbers
        for element in page.elements
    }
    findings = []
    candidates = {}

    for field in draft.fields:
        if field.field_id in candidates:
            findings.append(AuditFinding(
                document_id=document_id,
                field_id=field.field_id,
                finding_type=FindingType.CONFLICTING_VALUES,
                severity=FindingSeverity.ERROR,
                message="The model returned this field more than once.",
            ))
            continue

        field_definition = expected.get(field.field_id)
        if field_definition is None:
            findings.append(AuditFinding(
                document_id=document_id,
                field_id=field.field_id,
                finding_type=FindingType.UNKNOWN_FIELD,
                severity=FindingSeverity.WARNING,
                message="The model returned a field outside the selected form definition.",
            ))
            continue

        candidates[field.field_id] = field
        actual_kind = field.value.kind if field.value is not None else None
        if field.observation_status == ObservationStatus.OBSERVED and actual_kind != field_definition.kind.value:
            findings.append(AuditFinding(
                document_id=document_id,
                field_id=field.field_id,
                finding_type=FindingType.INVALID_VALUE,
                severity=FindingSeverity.ERROR,
                message=f"Expected {field_definition.kind.value}, received {actual_kind}.",
            ))

        valid_evidence = [
            elements[element_id]
            for element_id in field.evidence_element_ids
            if element_id in elements
        ]
        if field.observation_status != ObservationStatus.NOT_FOUND and not valid_evidence:
            findings.append(AuditFinding(
                document_id=document_id,
                field_id=field.field_id,
                finding_type=FindingType.MISSING_EVIDENCE,
                severity=FindingSeverity.ERROR,
                message="An observed, blank, or unreadable field needs source evidence.",
            ))
        if field.observation_status in {ObservationStatus.BLANK, ObservationStatus.UNREADABLE}:
            findings.append(AuditFinding(
                document_id=document_id,
                field_id=field.field_id,
                finding_type=FindingType.OTHER,
                severity=FindingSeverity.WARNING,
                message="Text extraction cannot confirm blank or unreadable fields; verify visually.",
            ))
        if len(valid_evidence) != len(field.evidence_element_ids):
            findings.append(AuditFinding(
                document_id=document_id,
                field_id=field.field_id,
                finding_type=FindingType.MISSING_EVIDENCE,
                severity=FindingSeverity.WARNING,
                message="Evidence must refer to elements on the selected K-1 page.",
            ))

    no_observed_values = bool(candidates) and not any(
        field.observation_status == ObservationStatus.OBSERVED
        for field in candidates.values()
    )
    if no_observed_values:
        findings.append(AuditFinding(
            document_id=document_id,
            finding_type=FindingType.OTHER,
            severity=FindingSeverity.WARNING,
            message="The model did not identify any observed values; review the extraction draft and prompt evidence.",
        ))

    tax_fields = []
    for field_definition in definition.fields:
        candidate = candidates.get(field_definition.id)
        if candidate is None:
            findings.append(AuditFinding(
                document_id=document_id,
                field_id=field_definition.id,
                finding_type=FindingType.MISSING_FIELD,
                severity=FindingSeverity.WARNING,
                message="The model did not return an outcome for this field.",
            ))
            tax_fields.append(TaxFormField(
                field_id=field_definition.id,
                observation_status=ObservationStatus.NOT_FOUND,
                status=ReviewStatus.NEEDS_REVIEW,
            ))
            continue

        evidence = [
            TaxEvidence(
                artifact_id=artifact.id,
                reason=candidate.reason,
                element_id=element.id,
                locations=element.locations,
                text=element.text,
            )
            for element_id in candidate.evidence_element_ids
            if (element := elements.get(element_id)) is not None
        ]
        invalid = any(
            finding.field_id == candidate.field_id
            and finding.severity == FindingSeverity.ERROR
            for finding in findings
        ) or candidate.observation_status in {ObservationStatus.BLANK, ObservationStatus.UNREADABLE} or (
            no_observed_values and candidate.observation_status == ObservationStatus.NOT_FOUND
        )
        tax_fields.append(TaxFormField(
            field_id=candidate.field_id,
            observation_status=candidate.observation_status,
            value=candidate.value,
            description=field_definition.source.labels[0],
            code=candidate.code,
            evidence=evidence,
            status=ReviewStatus.NEEDS_REVIEW if invalid else ReviewStatus.EXTRACTED,
        ))

    document = TaxDocument(
        id=document_id,
        source_document_id=artifact.source_document.id,
        document_type=definition.document_type,
        jurisdiction=definition.jurisdiction,
        form_id=definition.form_id,
        form_revision=definition.revision,
        tax_year=definition.tax_year,
        page_numbers=page_numbers,
        fields=tax_fields,
    )
    audit = AuditResult(
        document_id=document_id,
        form_id=definition.form_id,
        form_revision=definition.revision,
        tax_year=definition.tax_year,
        findings=findings,
        export_ready=False,
    )
    logger.info("Final document outcomes: %s", dict(Counter(field.status.value for field in tax_fields)))
    return Response(
        document=document,
        extraction_artifact=artifact,
        audit_result=audit,
    )
