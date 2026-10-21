"""Semantic fields reused by the first Utah K-1 definitions."""

from schemas.domain.forms.form_definition import (
    FieldDefinition,
    FieldSource,
    FieldTemplate,
    ValueKind,
)


FIELD_TEMPLATES = {
    "entity.ein": FieldTemplate(id="entity.ein", label="Issuing entity EIN", kind=ValueKind.TEXT),
    "entity.name_address": FieldTemplate(id="entity.name_address", label="Issuing entity name and address", kind=ValueKind.TEXT),
    "recipient.taxpayer_id": FieldTemplate(id="recipient.taxpayer_id", label="Recipient SSN or EIN", kind=ValueKind.TEXT),
    "recipient.name_address": FieldTemplate(id="recipient.name_address", label="Recipient name and address", kind=ValueKind.TEXT),
    "recipient.percent_ownership": FieldTemplate(id="recipient.percent_ownership", label="Recipient ownership percentage", kind=ValueKind.PERCENTAGE),
    "utah.ordinary_business_income_loss": FieldTemplate(id="utah.ordinary_business_income_loss", label="Utah ordinary business income/loss", kind=ValueKind.MONEY),
    "utah.net_rental_real_estate_income_loss": FieldTemplate(id="utah.net_rental_real_estate_income_loss", label="Utah net rental real estate income/loss", kind=ValueKind.MONEY),
    "utah.tax_withheld": FieldTemplate(id="utah.tax_withheld", label="Utah tax withheld for the recipient", kind=ValueKind.MONEY),
}


def field_definition(field_id: str, locator: str, label: str) -> FieldDefinition:
    """Bind a shared semantic field to this form revision's printed locator."""
    try:
        template = FIELD_TEMPLATES[field_id]
    except KeyError as exc:
        raise ValueError(f"Unknown semantic field: {field_id}") from exc
    return FieldDefinition(
        **template.model_dump(),
        source=FieldSource(printed_locator=locator, labels=[label]),
    )
