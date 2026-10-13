import base64
import binascii

from schemas.tax_document import K1Document
from pydantic import BaseModel, Field, field_validator


class UploadedFile(BaseModel):
    """One file transported as JSON-safe base64 text."""

    filename: str = Field(description="Original uploaded filename")
    content_base64: str = Field(description="Base64-encoded file contents")
    mime_type: str = Field(default="application/pdf", description="Uploaded file MIME type")

    @field_validator("content_base64")
    @classmethod
    def validate_base64(cls, value: str) -> str:
        try:
            base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("content_base64 must contain valid base64 data") from exc
        return value

class Request(BaseModel):
    """Files submitted as JSON-safe base64 data."""

    files: list[UploadedFile] = Field(min_length=1, description="Uploaded tax documents")

class Response(BaseModel):
    """
    Extracted outputs from agentic/model document processing
    """
    k1_document: K1Document

def solve(req: Request) -> Response:
    raise NotImplementedError("not implemented yet")
