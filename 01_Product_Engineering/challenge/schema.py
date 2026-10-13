import gradio as gr

from schemas.tax_document import K1Document
from pydantic import BaseModel, Field


class Request(BaseModel):
    """Files submitted through the UI."""

    files: list[gr.FileData] = Field(min_length=1, description="Uploaded tax documents")

class Response(BaseModel):
    """
    Extracted outputs from agentic/model document processing
    """
    k1_document: K1Document

def solve(req: Request) -> Response:
    for f in req.files:
        print(f"Name: {f.orig_name} {f.path}")
        print(f"Filesize bytes {f.size}")
    raise NotImplementedError("not implemented yet")
