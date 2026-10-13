from decimal import Decimal
from pydantic import StringConstraints, Field
from typing import Annotated

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
