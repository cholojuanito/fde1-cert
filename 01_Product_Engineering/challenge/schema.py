import gradio as gr

from schemas.domain.tax_document import TaxDocument
from schemas.extraction.extraction import SourceDocument
from schemas.common.enum import Parser
from extraction.parse import parse_document
from pydantic import BaseModel, Field


class Request(BaseModel):
    """Files submitted through the UI."""

    files: list[gr.FileData] = Field(min_length=1, description="Uploaded tax documents")

class Response(BaseModel):
    """
    Extracted outputs from agentic/model document processing
    """
    documents: list[TaxDocument] = Field(
        default_factory=list
    )
    source_documents: list[SourceDocument] = Field(
        default_factory=list
    )

def solve(req: Request) -> Response:
    # Parse/extraction info from docs
    parsed_docs = parse_document(Parser.DOCLING, req.files)
    print(parsed_docs)
    # Convert to common format
    # Let agent look over extraction, match form definition, audit, investigate, correct, reaudit
    return Response(documents=[])
