from pydantic import StringConstraints, Field, BaseModel
from typing import Annotated

USZipCode = Annotated[
    str,
    StringConstraints(pattern=r"^\d{5}(-\d{4})?$"),
]

class Address(BaseModel):
    street: str | None = None
    city: str | None = None
    state: str | None = Field(
        default=None,
        pattern=r"^[A-Z]{2}$",
        description="Two-letter US state code",
    )
    postal_code: USZipCode | None = None
