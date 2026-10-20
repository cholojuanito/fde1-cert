
from enum import StrEnum

from pydantic import BaseModel, Field

from schemas.common.enum import TaxDocumentType


class ValueKind(StrEnum):
    MONEY = "money"
    TEXT = "text"
    PERCENTAGE = "percentage"
    BOOLEAN = "boolean"
    COUNT = "count"


class FieldDefinition(BaseModel):
    id: str = Field(min_length=1)
    label: str
    kind: ValueKind
    required: bool = False
    repeated: bool = False
    source_labels: list[str] = Field(default_factory=list)
    source_codes: list[str] = Field(default_factory=list)


class FormDefinition(BaseModel):
    form_id: str
    document_type: TaxDocumentType
    jurisdiction: str
    tax_year: int
    fields: list[FieldDefinition]
