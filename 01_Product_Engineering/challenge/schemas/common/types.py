from decimal import Decimal
from pydantic import StringConstraints, Field, BaseModel, WithJsonSchema
from typing import Annotated, Literal

DECIMAL_PATTERN = r"^[+-]?[0-9]*\.?[0-9]+$"
SchemaDecimal = Annotated[
    Decimal,
    WithJsonSchema({"type": "number", "pattern": DECIMAL_PATTERN}),
]


EIN = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9]{2}-[0-9]{7}$"),
]

SSN = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9]{3}-[0-9]{2}-[0-9]{4}$"),
]
TaxPayerID = EIN | SSN

# 10 digit numbers and optional +1
USPhone = Annotated[
    str,
    StringConstraints(
        pattern=r"^(?:\+1[\s.-]?)?(?:\([0-9]{3}\)|[0-9]{3})[\s.-]?[0-9]{3}[\s.-]?[0-9]{4}$"
    ),
]

Percentage = Annotated[
    SchemaDecimal,
    Field(ge=0, le=100),
]

class MoneyValue(BaseModel):
    kind: Literal["money"] = "money"
    amount: SchemaDecimal


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
