from decimal import Decimal
from pydantic import StringConstraints, Field, BaseModel
from typing import Annotated, Literal

EIN = Annotated[
    str,
    StringConstraints(pattern=r"^\d{2}-\d{7}$"),
]

SSN = Annotated[
    str,
    StringConstraints(pattern=r"^\d{3}-\d{2}-\d{4}$"),
]
TaxPayerID = EIN | SSN

# 10 digit numbers and optional +1
USPhone = Annotated[
    str,
    StringConstraints(
        pattern=r"^(?:\+1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}$"
    ),
]

Percentage = Annotated[
    Decimal,
    Field(ge=0, le=100),
]

class MoneyValue(BaseModel):
    kind: Literal["money"] = "money"
    amount: Decimal


class TextValue(BaseModel):
    kind: Literal["text"] = "text"
    text: str


class PercentageValue(BaseModel):
    kind: Literal["percentage"] = "percentage"
    value: Percentage


class BooleanValue(BaseModel):
    kind: Literal["boolean"] = "boolean"
    value: bool


class CountValue(BaseModel):
    kind: Literal["count"] = "count"
    value: int


FieldValue = Annotated[
    MoneyValue
    | TextValue
    | PercentageValue
    | BooleanValue
    | CountValue,
    Field(discriminator="kind"),
]
