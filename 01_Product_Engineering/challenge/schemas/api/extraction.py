"""Compact result contracts for one uploaded tax PDF bundle."""

from pydantic import BaseModel, Field, model_validator

from schemas.audit.audit import FindingSeverity, FindingType
from schemas.common.enum import ObservationStatus, ReviewStatus
from schemas.common.types import FieldValue
from schemas.domain.bundle import BundleForm


class TaxFact(BaseModel):
    """A selected tax fact without parser- or model-specific diagnostics."""

    field_id: str = Field(
        min_length=1, description="Stable identifier for the extracted tax field."
    )
    observation_status: ObservationStatus = Field(
        description="Whether the source value was observed, blank, unreadable, or not found."
    )
    value: FieldValue | None = Field(
        default=None, description="Typed value when the field was observed."
    )
    qualifiers: dict[str, str] | None = Field(
        description="Dimensions of a repeated fact, i.e. cell values in a table",
        default=None,
    )
    code: str | None = Field(
        default=None,
        description="Printed tax code associated with the field, when present.",
    )
    status: ReviewStatus = Field(
        description="Current extraction or review status for this fact."
    )

    @model_validator(mode="after")
    def value_matches_observation_status(self):
        if self.observation_status == ObservationStatus.OBSERVED and self.value is None:
            raise ValueError("Observed facts must include a typed value")
        if (
            self.observation_status != ObservationStatus.OBSERVED
            and self.value is not None
        ):
            raise ValueError("Only observed facts may include a typed value")
        return self


class FormResult(BundleForm):
    """The selected facts for one logical form in the uploaded bundle."""

    facts: list[TaxFact] = Field(
        default_factory=list, description="Selected tax facts extracted from this form."
    )

    @model_validator(mode="after")
    def fact_ids_are_unique(self):
        fact_keys = [
            (
                fact.field_id,
                fact.code,
                tuple(sorted((fact.qualifiers or {}).items())),
            )
            for fact in self.facts
        ]
        if len(fact_keys) != len(set(fact_keys)):
            raise ValueError(
                "Facts must have unique field IDs, codes, and qualifiers within a form"
            )
        return self


class ExtractionIssue(BaseModel):
    """A compact, actionable extraction or review issue."""

    finding_type: FindingType = Field(description="Classification of the issue.")
    severity: FindingSeverity = Field(description="Impact level of the issue.")
    message: str = Field(
        min_length=1, description="Actionable explanation of the issue."
    )
    form_id: str | None = Field(
        default=None, description="Bundle-local form identifier affected by the issue."
    )
    field_id: str | None = Field(
        default=None, description="Tax field identifier affected by the issue."
    )


class BundleExtraction(BaseModel):
    """Result for one uploaded tax bundle."""

    forms: list[FormResult] = Field(
        default_factory=list,
        description="Forms and selected facts found in the PDF bundle.",
    )
    issues: list[ExtractionIssue] = Field(
        default_factory=list,
        description="Extraction and review issues requiring attention.",
    )

    @model_validator(mode="after")
    def references_are_to_known_forms(self):
        form_ids = {form.id for form in self.forms}
        if len(form_ids) != len(self.forms):
            raise ValueError("Bundle form IDs must be unique")

        for issue in self.issues:
            if issue.form_id is not None and issue.form_id not in form_ids:
                raise ValueError("Issue form_id must refer to a known form")
        return self
