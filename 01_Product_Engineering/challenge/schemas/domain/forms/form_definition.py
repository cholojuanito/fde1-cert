"""Contract for a versioned tax form definition."""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from schemas.common.enum import TaxDocumentType, TaxReturnType


class ValueKind(StrEnum):
    MONEY = "money"
    TEXT = "text"
    PERCENTAGE = "percentage"
    BOOLEAN = "boolean"
    COUNT = "count"


class FieldSource(BaseModel):
    """Printed locator in a specific form revision."""

    printed_locator: str = Field(min_length=1)
    labels: list[str] = Field(min_length=1)


class FieldTemplate(BaseModel):
    """Stable semantic meaning and value kind, independent of printed layout."""

    id: str = Field(min_length=1)
    label: str
    kind: ValueKind


class FieldDefinition(FieldTemplate):
    source: FieldSource


class FormDefinition(BaseModel):
    form_id: str
    return_type: TaxReturnType
    schedule: str
    jurisdiction: str
    tax_year: int = Field(ge=1900)
    revision: str
    recipient_role: str
    document_type: TaxDocumentType
    fields: list[FieldDefinition]

    @model_validator(mode="after")
    def field_ids_are_unique(self):
        ids = [field.id for field in self.fields]
        if len(ids) != len(set(ids)):
            raise ValueError("Form definition field IDs must be unique")
        return self
