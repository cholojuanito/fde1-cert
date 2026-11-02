"""Internal-neutral models for describing logical forms in one PDF bundle."""

from pydantic import BaseModel, Field, model_validator

from schemas.common.enum import TaxDocumentType


class BundleForm(BaseModel):
    """One logical form or statement discovered within an uploaded PDF."""

    id: str = Field(min_length=1, description="Bundle-local identifier for this form.")
    document_type: TaxDocumentType = Field(description="Category of tax document.")
    form_id: str | None = Field(default=None, description="Printed form identifier.")
    jurisdiction: str | None = Field(
        default=None, description="Tax jurisdiction that issued the form."
    )
    tax_year: int | None = Field(
        default=None, ge=1900, description="Tax year reported by the form."
    )
    page_numbers: list[int] = Field(
        min_length=1, description="One-indexed PDF pages belonging to this form."
    )

    @model_validator(mode="after")
    def page_numbers_are_unique(self):
        if any(page < 1 for page in self.page_numbers):
            raise ValueError("Page numbers must be positive")
        if len(self.page_numbers) != len(set(self.page_numbers)):
            raise ValueError("Page numbers must be unique within a form")
        return self


