"""Small registry for identifying and creating the supported Utah K-1 definitions."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from schemas.common.enum import TaxDocumentType, TaxReturnType
from schemas.domain.forms.field_templates import field_definition
from schemas.domain.forms.form_definition import FormDefinition
from schemas.extraction.extraction import ExtractionArtifact


class FormIdentity(BaseModel):
    return_type: TaxReturnType
    tax_year: int = Field(ge=1900)
    schedule: str | None = None
    page_numbers: list[int] = Field(default_factory=list)


class UnsupportedFormDefinition(ValueError):
    """A recognized return type or year does not have a supported definition."""


# Each annual mapping changes only the printed locator and label. The semantic
# field IDs and value kinds come from field_templates.py.
def _partnership_fields(ownership_box: str, withholding_line: str):
    return {
        "entity.ein": ("A", "Partnership's EIN"),
        "entity.name_address": ("B", "Partnership's name, address, city, state, and ZIP code"),
        "recipient.taxpayer_id": ("C", "Partner's SSN or EIN"),
        "recipient.name_address": ("D", "Partner's name, address, city, state, and ZIP code"),
        "recipient.percent_ownership": (ownership_box, "Percent of ownership"),
        "utah.ordinary_business_income_loss": ("1", "Utah ordinary business income/loss"),
        "utah.net_rental_real_estate_income_loss": ("2", "Utah net rental real estate income/loss"),
        "utah.tax_withheld": (withholding_line, "Utah tax withheld on behalf of partner"),
    }


def _scorporation_fields(ownership_box: str):
    return {
        "entity.ein": ("A", "S-corporation's EIN"),
        "entity.name_address": ("B", "S-corporation's name, address, city, state, and ZIP code"),
        "recipient.taxpayer_id": ("C", "Shareholder's SSN or EIN"),
        "recipient.name_address": ("D", "Shareholder's name, address, city, state, and ZIP code"),
        "recipient.percent_ownership": (ownership_box, "Percent of ownership"),
        "utah.ordinary_business_income_loss": ("1", "Utah ordinary business income/loss"),
        "utah.net_rental_real_estate_income_loss": ("2", "Utah net rental real estate income/loss"),
        "utah.tax_withheld": ("20", "Utah tax withheld on behalf of shareholder"),
    }


_FORM_MAPPINGS = {
    (TaxReturnType.UTAH_TC65, 2024): _partnership_fields("F", "19"),
    (TaxReturnType.UTAH_TC65, 2025): _partnership_fields("H", "19"),
    (TaxReturnType.UTAH_TC20S, 2024): _scorporation_fields("E"),
    (TaxReturnType.UTAH_TC20S, 2025): _scorporation_fields("G"),
}

_FORM_IDS = {
    TaxReturnType.UTAH_TC65: ("ut_tc65_schedule_k1", "partner"),
    TaxReturnType.UTAH_TC20S: ("ut_tc20s_schedule_k1", "shareholder"),
}


def create_form_definition(identity: FormIdentity) -> FormDefinition:
    """Return a fresh definition for one registered return, schedule, and year."""
    if identity.schedule != "K-1":
        raise UnsupportedFormDefinition(
            f"Recognized Utah {identity.return_type.value} return; K-1 extraction requires a K-1 schedule"
        )
    try:
        mapping = _FORM_MAPPINGS[(identity.return_type, identity.tax_year)]
        form_id, recipient_role = _FORM_IDS[identity.return_type]
    except KeyError as exc:
        raise UnsupportedFormDefinition(
            f"No {identity.return_type.value} K-1 definition for tax year {identity.tax_year}"
        ) from exc

    return FormDefinition(
        form_id=form_id,
        return_type=identity.return_type,
        schedule="K-1",
        jurisdiction="UT",
        tax_year=identity.tax_year,
        revision=f"{identity.tax_year}-original",
        recipient_role=recipient_role,
        document_type=TaxDocumentType.STATE_K1,
        fields=[field_definition(field_id, *source) for field_id, source in mapping.items()],
    )


def identify_form(text: str, filename: str = "") -> FormIdentity:
    """Identify a form from its extracted title; use filename only for the year."""
    normalized = " ".join(text.casefold().replace("–", "-").split())
    year_match = re.search(r"\b(20\d{2})\b", f"{text} {filename}")
    if not year_match:
        raise ValueError("Could not determine the tax year from the form or filename")
    year = int(year_match.group(1))

    if "tc-20s" in normalized:
        if "k-1" in normalized and ("shareholder" in normalized or "sch." in normalized):
            return FormIdentity(return_type=TaxReturnType.UTAH_TC20S, tax_year=year, schedule="K-1")
        return FormIdentity(return_type=TaxReturnType.UTAH_TC20S, tax_year=year)
    if "tc-65" in normalized:
        if "k-1" in normalized and ("partner" in normalized or "sch." in normalized):
            return FormIdentity(return_type=TaxReturnType.UTAH_TC65, tax_year=year, schedule="K-1")
        return FormIdentity(return_type=TaxReturnType.UTAH_TC65, tax_year=year)
    if "tc-20" in normalized and "corporation" in normalized:
        return FormIdentity(return_type=TaxReturnType.UTAH_TC20, tax_year=year)
    raise ValueError("Docling did not extract a supported Utah form title")


def identify_artifact_form(artifact: ExtractionArtifact) -> FormIdentity:
    """Identify exactly one K-1 by page heading; reject bundles with multiple K-1s."""
    identities = []
    for page in artifact.pages:
        text = " ".join(element.text or "" for element in page.elements)
        try:
            identity = identify_form(text, artifact.source_document.filename)
        except ValueError:
            continue
        if identity.schedule == "K-1":
            identities.append(identity.model_copy(update={"page_numbers": [page.page_number]}))

    if len(identities) > 1:
        raise ValueError("This MVP accepts one K-1 per PDF; multiple K-1 pages were detected")
    if identities:
        return identities[0]

    # Recognize a TC-20 return separately so it does not get treated as a K-1.
    text = " ".join(element.text or "" for page in artifact.pages for element in page.elements)
    return identify_form(text, artifact.source_document.filename)


def require_readable_fields(
    artifact: ExtractionArtifact,
    definition: FormDefinition,
    page_numbers: list[int],
) -> None:
    """Fail before the model call if parser output lacks field-level text."""
    page_text = " ".join(
        element.text or ""
        for page in artifact.pages
        if page.page_number in page_numbers
        for element in page.elements
    )
    normalized_text = " ".join(page_text.casefold().split())
    matching_fields = sum(
        any(" ".join(label.casefold().split()) in normalized_text for label in field.source.labels)
        for field in definition.fields
    )
    if matching_fields < 2:
        raise ValueError(
            f"Docling extracted too little form text from {artifact.source_document.filename}; "
            "verify the PDF is readable or change the parser configuration"
        )
