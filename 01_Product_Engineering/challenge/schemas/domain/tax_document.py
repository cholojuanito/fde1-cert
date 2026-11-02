from __future__ import annotations


from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..common.enum import ObservationStatus, ReviewStatus, TaxDocumentType
from ..common.types import FieldValue
from ..extraction.extraction import SourceLocation
from .bundle import BundleForm
from ..api.extraction import ExtractionIssue, TaxFact


class TaxEvidence(BaseModel):
    """Legacy detailed evidence contract retained for non-extraction callers."""

    artifact_id: str
    element_id: str | None = None
    reason: str = Field(description="Agent reasoning for evidence")
    locations: list[SourceLocation] = Field(default_factory=list)
    text: str | None = Field(description="Text from document")


class TaxFormField(BaseModel):
    """Legacy detailed field contract retained for non-extraction callers."""

    field_id: str
    observation_status: ObservationStatus
    value: FieldValue | None = Field(description="Form field value", default=None)
    description: str | None = Field(description="Form field description", default=None)
    code: str | None = Field(description="Form field code, if applicable", default=None)
    qualifiers: dict[str, str] = Field(default_factory=dict)
    evidence: list[TaxEvidence] = Field(default_factory=list)
    status: ReviewStatus = ReviewStatus.EXTRACTED


class TaxDocument(BaseModel):
    """Legacy detailed document contract retained for non-extraction callers."""

    id: str
    source_document_id: str
    document_type: TaxDocumentType
    jurisdiction: str
    form_id: str | None = None
    form_revision: str | None = None
    tax_year: int | None = None
    page_numbers: list[int] = Field(default_factory=list)
    issuing_entity_id: str | None = None
    receiving_entity_id: str | None = None
    fields: list[TaxFormField] = Field(default_factory=list)


class PrintedLocator(BaseModel):
    section: str | None = None
    box: str | None = None
    label: str = Field(min_length=1)
    row: str | None = None
    column: str | None = None


class FactSource(BaseModel):
    element_id: str = Field(min_length=1)
    locations: list[SourceLocation]
    text: str
    locator: PrintedLocator


class FactReference(BaseModel):
    form_id: str = Field(min_length=1)
    fact_id: str = Field(min_length=1)


class FactRelationship(BaseModel):
    source: FactReference
    target: FactReference
    relationship: str = Field(min_length=1)
    evidence: list[FactSource] = Field(default_factory=list)
    status: ReviewStatus = ReviewStatus.NEEDS_REVIEW


class BundleLinksDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relationships: list[FactRelationship] = Field(default_factory=list)


class ProcessedFact(BaseModel):
    id: str = Field(min_length=1)
    fact: TaxFact
    description: str | None = None
    sources: list[FactSource] = Field(default_factory=list)


class ProcessedForm(BaseModel):
    form: BundleForm
    facts: list[ProcessedFact] = Field(default_factory=list)

    @model_validator(mode="after")
    def fact_ids_are_unique(self):
        if len({fact.id for fact in self.facts}) != len(self.facts):
            raise ValueError("Processed fact IDs must be unique within a form")
        return self


class ProcessedBundle(BaseModel):
    forms: list[ProcessedForm] = Field(default_factory=list)
    issues: list[ExtractionIssue] = Field(default_factory=list)
    relationships: list[FactRelationship] = Field(default_factory=list)

    @model_validator(mode="after")
    def references_are_valid(self):
        form_ids = {form.form.id for form in self.forms}
        if len(form_ids) != len(self.forms):
            raise ValueError("Processed form IDs must be unique")
        known_facts = {
            (form.form.id, fact.id) for form in self.forms for fact in form.facts
        }
        for issue in self.issues:
            if issue.form_id is not None and issue.form_id not in form_ids:
                raise ValueError("Issue form_id must refer to a known form")
        for relationship in self.relationships:
            if (
                relationship.source.form_id,
                relationship.source.fact_id,
            ) not in known_facts:
                raise ValueError("Relationship source must refer to a known fact")
            if (
                relationship.target.form_id,
                relationship.target.fact_id,
            ) not in known_facts:
                raise ValueError("Relationship target must refer to a known fact")
        return self


class EvidenceSpanDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_id: str = Field(min_length=1)
    end_id: str = Field(min_length=1)


class DiscoveredSectionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    spans: list[EvidenceSpanDraft] = Field(min_length=1)
    evidence_element_ids: list[str] = Field(default_factory=list)


class DiscoveredFormDraft(BundleForm):
    model_config = ConfigDict(extra="forbid")
    sections: list[DiscoveredSectionDraft] = Field(default_factory=list)
    evidence_element_ids: list[str] = Field(default_factory=list)
    expected_page_count: int | None = Field(default=None, ge=1)


class FormDiscoveryDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    forms: list[DiscoveredFormDraft] = Field(default_factory=list)
    issues: list[ExtractionIssue] = Field(default_factory=list)


class FactDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    field_id: str = Field(min_length=1)
    description: str | None = None
    observation_status: ObservationStatus
    value: FieldValue | None = None
    code: str | None = None
    qualifiers: dict[str, str] = Field(default_factory=dict)
    locator: PrintedLocator
    evidence_element_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def value_only_when_observed(self):
        if self.observation_status == ObservationStatus.OBSERVED and self.value is None:
            raise ValueError("Observed fields must include a typed value")
        if (
            self.observation_status != ObservationStatus.OBSERVED
            and self.value is not None
        ):
            raise ValueError("Only observed fields may include a typed value")
        return self


class FormExtractionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facts: list[FactDraft] = Field(default_factory=list)
    issues: list[ExtractionIssue] = Field(default_factory=list)


class FieldExtractionDraft(BaseModel):
    """Known-form extraction result retained for the existing Utah endpoint."""

    model_config = ConfigDict(extra="forbid")
    field_id: str = Field(min_length=1)
    observation_status: ObservationStatus
    value: FieldValue | None = None
    reason: str = Field(min_length=1)
    description: str | None = None
    code: str | None = None
    evidence_element_ids: list[str] = Field(default_factory=list)
    evidence_text: str | None = None

    @model_validator(mode="after")
    def value_only_when_observed(self):
        if self.observation_status == ObservationStatus.OBSERVED and self.value is None:
            raise ValueError("Observed fields must include a typed value")
        if (
            self.observation_status != ObservationStatus.OBSERVED
            and self.value is not None
        ):
            raise ValueError("Only observed fields may include a typed value")
        return self


class TaxExtractionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    form_id: str = Field(min_length=1)
    tax_year: int = Field(ge=1900)
    fields: list[FieldExtractionDraft] = Field(default_factory=list)
