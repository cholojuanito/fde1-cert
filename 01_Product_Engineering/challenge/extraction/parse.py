from schemas.common.enum import Parser
from gradio import FileData

def _parse_with_docling(files:list[FileData]) -> dict[str, dict]:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions, PdfBackend
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options = TableStructureOptions(do_cell_matching=True)
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    parsed_docs = {}
    for file in files:
        if not file.orig_name in parsed_docs:
            parsed_docs[file.orig_name] = {}
        result = converter.convert(file.path)
        parsed_docs[file.orig_name] = result.model_dump(mode="json")
    return parsed_docs


def _parse_with_liteparse(files:list[FileData]) -> dict[str, dict]:
    raise NotImplementedError()

PARSERS = {
    Parser.DOCLING: _parse_with_docling,
    Parser.LITEPARSE: _parse_with_liteparse
}

def parse_document(parser:Parser, files:list[FileData]) -> dict[str, dict] | None:
    callable = PARSERS.get(parser, None)
    if callable:
        return callable(files)
    else:
        return None
