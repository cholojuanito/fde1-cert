from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from ..common.enum import DocumentElementType, ExtractionMethod, Parser, ExtractionArtifactFormat, ExtractionArtifactStatus

class BoundingBox(BaseModel):
    # Top-left origin
    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def validate_coordinates(self):
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("Invalid bounding box coordinates")
        return self

class SourceLocation(BaseModel):
    page: int = Field(ge=1)
    bbox: BoundingBox | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_char_span(self):
        if self.char_start is not None and self.char_end is not None:
            if self.char_end < self.char_start:
                raise ValueError("char_end must be >= char_start")
        return self

class DocumentElement(BaseModel):
    id: str
    artifact_id: str
    kind: DocumentElementType
    text: str | None
    locations: list[SourceLocation] = Field(
        min_length=1
    )
    extraction_method: ExtractionMethod = ExtractionMethod.UNKNOWN
    confidence: float | None = Field(
        description="Text extraction confidence level", default=None, ge=0, le=1
    )
    image_uri: str | None = None
    extractor_label: str | None = None
    extractor_ref: str | None = None

class SourceDocument(BaseModel):
    id: str
    filename: str
    sha256: str
    page_count: int
    storage_uri: str

class ExtractedPage(BaseModel):
    artifact_id: str
    page_number: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    image_uri: str | None = None # Optional separately rendered or extracted image
    warnings: list[str] = Field(default_factory=list)
    elements: list[DocumentElement] = Field(default_factory=list)

class ExtractionArtifact(BaseModel):
    id: str
    source_document: SourceDocument
    parser: Parser
    parser_version: str
    config_hash: str
    status: ExtractionArtifactStatus
    format: ExtractionArtifactFormat
    created_at: datetime
    output_uri: str | None # Full parser output
    pages: list[ExtractedPage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
