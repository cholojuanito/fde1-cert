from typing import Annotated
from datetime import date
from decimal import Decimal
from .address import Address
from .types import EIN, TaxPayerID, USPhone
from .enum import EntityCode
from pydantic import BaseModel, Field

class Partnership(BaseModel):
    name: str = Field(description="Organization's name")
    ein: EIN = Field(
        description="Employer Identification Number",
    )
    address: Address = Field(default_factory=Address)

class Partner(BaseModel):
    name: str = Field(description="Line D: partner name")
    address: Address = Field(description="Primary address of individual")
    taxpayer_id: TaxPayerID = Field(description="Line C: partner SSN or EIN.")
    phone: USPhone = Field(
        description="US phone number",
    )
    percent_ownership: Decimal = Field(
        description="Percentage ownership of partnership (0-100%)",
        ge=0,
        le=100,
    )
    limited_partner: bool = Field(description="Is limited partner?")
    entity_code: EntityCode = Field(description="The type of partnership")
    date_of_affiliation: date = Field(description="Date partner began to be involved in partnership")
    date_of_withdrawl: date | None = Field(
        description="Date partner left the partnership",
        default=None
    )
