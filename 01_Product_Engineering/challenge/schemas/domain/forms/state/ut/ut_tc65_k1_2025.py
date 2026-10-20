"""Initial supported-field subset for Utah's 2025 TC-65 Schedule K-1."""

from schemas.domain.forms.form_definition import FieldDefinition, FormDefinition, ValueKind
from schemas.common.enum import TaxDocumentType


UT_TC65_K1_2025 = FormDefinition(
    form_id="ut_tc65_schedule_k1",
    document_type=TaxDocumentType.STATE_K1,
    jurisdiction="UT",
    tax_year=2025,
    fields=[
        FieldDefinition(id="partnership.ein", label="Partnership EIN", kind=ValueKind.TEXT, source_labels=["Partnership's EIN"], source_codes=["A"]),
        FieldDefinition(id="partnership.name_address", label="Partnership name and address", kind=ValueKind.TEXT, source_labels=["Partnership's name, address, city, state, and ZIP code"], source_codes=["B"]),
        FieldDefinition(id="partner.tin", label="Partner SSN or TIN", kind=ValueKind.TEXT, source_labels=["Partner's SSN or TIN"], source_codes=["C"]),
        FieldDefinition(id="partner.name_address", label="Partner name and address", kind=ValueKind.TEXT, source_labels=["Name, address, city, state, and ZIP code for partner entered in C"], source_codes=["D"]),
        FieldDefinition(id="partner.percent_ownership", label="Percent of ownership", kind=ValueKind.PERCENTAGE, source_labels=["Percent of ownership"], source_codes=["H"]),
        FieldDefinition(id="utah.ordinary_business_income_loss", label="Utah ordinary business income/loss", kind=ValueKind.MONEY, source_labels=["Utah ordinary business income/loss"], source_codes=["1"]),
        FieldDefinition(id="utah.net_rental_real_estate_income_loss", label="Utah net rental real estate income/loss", kind=ValueKind.MONEY, source_labels=["Utah net rental real estate income/loss"], source_codes=["2"]),
        FieldDefinition(id="utah.tax_withheld", label="Utah tax withheld on behalf of partner", kind=ValueKind.MONEY, source_labels=["Utah tax withheld on behalf of partner"], source_codes=["19"]),
    ],
)
