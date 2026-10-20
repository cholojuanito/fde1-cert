from uuid import uuid4

import gradio as gr
from pydantic import BaseModel, Field

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
    Parser,
    ReviewStatus,
    TaxDocumentType,
)
from schemas.domain.forms.state.ut.ut_tc65_k1_2025 import UT_TC65_K1_2025
from schemas.domain.tax_document import TaxDocument, TaxEvidence, TaxFormField
from schemas.extraction.extraction import ExtractionArtifact, SourceDocument


class Request(BaseModel):
    """Files submitted through the UI."""

    files: list[gr.FileData] = Field(min_length=1, description="Uploaded tax documents")

class Response(BaseModel):
    """
    Extracted outputs from agentic/model document processing
    """
    documents: list[TaxDocument] = Field(
        default_factory=list
    )
    source_documents: list[SourceDocument] = Field(
        default_factory=list
    )
    extraction_artifacts: list[ExtractionArtifact] = Field(default_factory=list)
    audit_results: list[AuditResult] = Field(default_factory=list)

def solve(req: Request) -> Response:
    parsed_files = parse_document(Parser.DOCLING, req.files)
    documents = []
    sources = []
    artifacts = []
    audits = []

    for parsed_file in parsed_files:
        artifact = adapter_for(Parser.DOCLING).adapt(parsed_file)
        artifacts.append(artifact)
        sources.append(artifact.source_document)
        document_text = " ".join(
            element.text or ""
            for page in artifact.pages
            for element in page.elements
        ).casefold()
        # if "tc-65" not in document_text or "k-1" not in document_text or "2025" not in document_text:
        #     raise ValueError(
        #         f"{artifact.source_document.filename} does not appear to be a 2025 Utah TC-65 Schedule K-1"
        #     )
        draft = extract_tax_fields(artifact, UT_TC65_K1_2025)
        if draft.form_id != UT_TC65_K1_2025.form_id or draft.tax_year != UT_TC65_K1_2025.tax_year:
            raise ValueError("The model's form identification does not match the selected definition")

        document_id = str(uuid4())
        expected = {field.id: field for field in UT_TC65_K1_2025.fields}
        elements = {
            element.id: element
            for page in artifact.pages
            for element in page.elements
        }
        by_id = {}
        findings = []
        for field in draft.fields:
            if field.field_id in by_id:
                findings.append(AuditFinding(
                    document_id=document_id,
                    field_id=field.field_id,
                    finding_type=FindingType.CONFLICTING_VALUES,
                    severity=FindingSeverity.ERROR,
                    message="The model returned this field more than once.",
                ))
                continue
            by_id[field.field_id] = field
            definition = expected.get(field.field_id)
            if definition is None:
                findings.append(AuditFinding(
                    document_id=document_id,
                    field_id=field.field_id,
                    finding_type=FindingType.UNKNOWN_FIELD,
                    severity=FindingSeverity.WARNING,
                    message="The model returned a field outside the selected form definition.",
                ))
                continue
            expected_kind = definition.kind.value
            actual_kind = field.value.kind if field.value is not None else None
            if field.observation_status == ObservationStatus.OBSERVED and actual_kind != expected_kind:
                findings.append(AuditFinding(
                    document_id=document_id,
                    field_id=field.field_id,
                    finding_type=FindingType.INVALID_VALUE,
                    severity=FindingSeverity.ERROR,
                    message=f"Expected a {expected_kind} value, received {actual_kind}.",
                ))
            valid_elements = [elements[item_id] for item_id in field.evidence_element_ids if item_id in elements]
            if len(valid_elements) != len(field.evidence_element_ids):
                findings.append(AuditFinding(
                    document_id=document_id,
                    field_id=field.field_id,
                    finding_type=FindingType.MISSING_EVIDENCE,
                    severity=FindingSeverity.WARNING,
                    message="One or more evidence references did not resolve to parser elements.",
                ))
            if not valid_elements and field.observation_status == ObservationStatus.OBSERVED:
                findings.append(AuditFinding(
                    document_id=document_id,
                    field_id=field.field_id,
                    finding_type=FindingType.MISSING_EVIDENCE,
                    severity=FindingSeverity.ERROR,
                    message="An observed value needs source evidence.",
                ))

        tax_fields = []
        for field_definition in UT_TC65_K1_2025.fields:
            candidate = by_id.get(field_definition.id)
            if candidate is None:
                candidate_status = ObservationStatus.NOT_FOUND
                findings.append(AuditFinding(
                    document_id=document_id,
                    field_id=field_definition.id,
                    finding_type=FindingType.MISSING_FIELD,
                    severity=FindingSeverity.WARNING,
                    message="The model did not return an outcome for this defined field.",
                ))
                tax_fields.append(TaxFormField(
                    field_id=field_definition.id,
                    observation_status=candidate_status,
                    status=ReviewStatus.NEEDS_REVIEW,
                ))
                continue
            evidence = []
            for element_id in candidate.evidence_element_ids:
                element = elements.get(element_id)
                if element:
                    evidence.append(TaxEvidence(
                        artifact_id=artifact.id,
                        element_id=element.id,
                        locations=element.locations,
                        text=element.text,
                    ))
            is_invalid = any(
                finding.field_id == candidate.field_id
                and finding.severity == FindingSeverity.ERROR
                for finding in findings
            )
            tax_fields.append(TaxFormField(
                field_id=candidate.field_id,
                observation_status=candidate.observation_status,
                value=candidate.value,
                description=candidate.description,
                code=candidate.code,
                evidence=evidence,
                status=ReviewStatus.NEEDS_REVIEW if is_invalid else ReviewStatus.EXTRACTED,
            ))

        documents.append(TaxDocument(
            id=document_id,
            source_document_id=artifact.source_document.id,
            document_type=TaxDocumentType.STATE_K1,
            jurisdiction="UT",
            form_id=UT_TC65_K1_2025.form_id,
            tax_year=2025,
            page_numbers=[page.page_number for page in artifact.pages],
            fields=tax_fields,
        ))
        audits.append(AuditResult(
            document_id=document_id,
            form_id=UT_TC65_K1_2025.form_id,
            findings=findings,
            export_ready=False,
        ))

    return Response(
        documents=documents,
        source_documents=sources,
        extraction_artifacts=artifacts,
        audit_results=audits,
    )
