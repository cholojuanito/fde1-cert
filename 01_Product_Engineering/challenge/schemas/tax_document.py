from decimal import Decimal
from pydantic import BaseModel, Field, model_validator
from .common.enum import State
from .common.identity import Partnership, Partner
from .states.utah.base import UtahK1TaxLinesBase

class Allocation(BaseModel):
    state_share: Decimal = Field(ge=0)
    total: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def state_lte_total(self):
        if self.state_share > self.total:
            raise ValueError("state_share cannot exceed total assets")
        return self

class ApportionmentFactors(BaseModel):
    property: Allocation
    payroll: Allocation
    sales: Allocation

class K1Document(BaseModel):
    tax_year: int = Field(
        description="Tax year this document is for",
        strict=True,
        gt=1900,
        lt=2100 # todo: dynamically set to +1 current tax year
    )
    state: State
    partnership: Partnership
    partner: Partner
    apportionment_factors: ApportionmentFactors
    tax_lines: UtahK1TaxLinesBase
