from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..common.enum import TaxDocumentType, ReviewStatus, ObservationStatus
from ..common.types import FieldValue
from ..extraction.extraction import SourceLocation

class TaxEvidence(BaseModel):
    """Source evidence supporting an extracted tax value."""
    artifact_id: str
    element_id: str | None = None
    reason: str = Field(description="Agent reasoning for evidence")
    locations: list[SourceLocation] = Field(default_factory=list)
    text: str | None = Field(description="Text from document")

class TaxFormField(BaseModel):
    """An extracted tax field"""
    field_id: str
    observation_status: ObservationStatus
    value: FieldValue | None = Field(description="Form field value", default=None)
    description: str | None = Field(description="Form field description", default=None)
    code: str | None = Field(description="Form field code, if applicable", default=None)
    qualifiers: dict[str, str] = Field(default_factory=dict)
    evidence: list[TaxEvidence] = Field(default_factory=list)
    status: ReviewStatus = ReviewStatus.EXTRACTED


class FieldExtractionDraft(BaseModel):
    """Untrusted model proposal; evidence references are checked by the caller."""
    model_config = ConfigDict(extra="forbid")

    field_id: str
    observation_status: ObservationStatus
    value: FieldValue | None = None
    reason: str = Field(description="Cited reason the evidence supports this extraction")
    description: str | None = Field(description="Form field description", default=None)
    code: str | None = None
    evidence_element_ids: list[str] = Field(default_factory=list)
    evidence_text: str | None = None

    @model_validator(mode="after")
    def value_only_when_observed(self):
        if self.observation_status == ObservationStatus.OBSERVED and self.value is None:
            raise ValueError("Observed fields must include a typed value")
        if self.observation_status != ObservationStatus.OBSERVED and self.value is not None:
            raise ValueError("Only observed fields may include a typed value")
        return self


class TaxExtractionDraft(BaseModel):
    """Structured, untrusted response from the extraction model."""
    model_config = ConfigDict(extra="forbid")

    form_id: str
    tax_year: int
    fields: list[FieldExtractionDraft]

class TaxDocument(BaseModel):
    """A tax form within a larger tax bundle or source document"""
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
