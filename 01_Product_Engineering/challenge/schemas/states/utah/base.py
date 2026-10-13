from decimal import Decimal
from pydantic import BaseModel, Field

class DescribedAmount(BaseModel):
    description: str | None = None
    amount: Decimal | None = None

class ConditionalAmount(BaseModel):
    condition_checked: bool
    amount: Decimal | None = None

class UtahK1TaxLinesBase(BaseModel):
    business_income_loss: Decimal | None = Field(
        default=None,
        description="Utah ordinary business income/loss",
    )
    real_estate_income_loss: Decimal | None = Field(
        default=None,
        description="Utah net rental real estate income/loss",
    )
    other_rental_income_loss: Decimal | None = Field(
        default=None,
        description="Utah other net rental income/loss",
    )
    guaranteed_payments: Decimal | None = Field(
        default=None,
        description="Utah guaranteed payments",
    )
    us_government_interest_income: Decimal | None = Field(
        default=None,
        description="US government interest income",
    )
    municipal_bond_interest_income: Decimal | None = Field(
        default=None,
        description="Utah municipal bond interest income",
    )
    other_bond_interest_income: Decimal | None = Field(
        default=None,
        description="Utah other bond interest income",
    )
    dividends: Decimal | None = Field(
        default=None,
        description="Utah dividends",
    )
    royalties: Decimal | None = Field(
        default=None,
        description="Utah royalties",
    )
    short_term_capital_gain_loss: Decimal | None = Field(
        default=None,
        description="Utah net short-term capital gain/loss",
    )
    long_term_capital_gain_loss: Decimal | None = Field(
        default=None,
        description="Utah net long-term capital gain/loss",
    )
    section_1231_gain_loss: Decimal | None = Field(
        default=None,
        description="Utah Net Section 1231 Gain/Loss",
    )
    recapture_of_section_179: Decimal | None = Field(
        default=None,
        description="Recapture of Section 179 Deduction",
    )
    other_income_loss: list[DescribedAmount] = Field(
        default_factory=list,
        description="Utah other income/loss"
    )
    section_179_deduction: Decimal | None = Field(
        default=None,
        description="Utah Section 179 Deduction",
    )
    contributions: Decimal | None = Field(
        default=None,
        description="Utah contributions",
    )
    foreign_taxes_paid_accrued: Decimal | None = Field(
        default=None,
        description="Foreign Taxes Paid or Accrued",
    )
    other_deductions: list[DescribedAmount] = Field(
        default_factory=list,
        description="Utah other deductions"
    )
    nonrefundable_credits: list[DescribedAmount] = Field(
        default_factory=list,
        description="Utah nonrefundable credits"
    )
    refundable_credits: list[DescribedAmount] = Field(
        default_factory=list,
        description="Utah refundable credits"
    )
    tax_withheld_on_behalf: ConditionalAmount = Field(
        description="Utah Tax Withheld on Behalf of Partner"
    )
