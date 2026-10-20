from pydantic import BaseModel, Field

from ..common.enum import TaxDocumentType, ReviewStatus
from ..common.types import FieldValue
from ..extraction.extraction import SourceLocation

class TaxEvidence(BaseModel):
    """Source evidence supporting an extracted tax value."""
    artifact_id: str
    element_id: str | None = None
    locations: list[SourceLocation] = Field(default_factory=list)
    text: str | None = None

class TaxFormField(BaseModel):
    """An extracted tax field"""
    field_id: str
    value: FieldValue | None = Field(description="Form field value", default=None)
    description: str | None = Field(description="Form field description", default=None)
    code: str | None = Field(description="Form field code, if applicable", default=None)
    qualifiers: dict[str, str] = Field(default_factory=dict)
    evidence: list[TaxEvidence] = Field(default_factory=list)
    status: ReviewStatus = ReviewStatus.EXTRACTED

class TaxDocument(BaseModel):
    """A tax form within a larger tax bundle or source document"""
    id: str
    source_document_id: str
    document_type: TaxDocumentType
    jurisdiction: str
    form_id: str | None = None
    tax_year: int | None = None
    page_numbers: list[int] = Field(default_factory=list)
    issuing_entity_id: str | None = None
    receiving_entity_id: str | None = None
    fields: list[TaxFormField] = Field(default_factory=list)
