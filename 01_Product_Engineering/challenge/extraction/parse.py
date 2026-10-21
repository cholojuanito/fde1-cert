from dataclasses import dataclass
from gradio import FileData

from schemas.common.enum import Parser


@dataclass
class ParsedFile:
    filename: str
    path: str
    result: object


def _parse_with_docling(files: list[FileData]) -> list[ParsedFile]:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import OcrMode, PdfPipelineOptions, TableStructureOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.ocr_options.mode = OcrMode.FULL_PAGE
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options = TableStructureOptions(do_cell_matching=True)
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )
    return [
        ParsedFile(file.orig_name, file.path, converter.convert(file.path))
        for file in files
    ]


def _parse_with_liteparse(files: list[FileData]) -> list[ParsedFile]:
    from liteparse import LiteParse

    parser = LiteParse(output_format="json", extract_blocks=True, ocr_enabled=False)
    return [
        ParsedFile(file.orig_name, file.path, parser.parse(file.path))
        for file in files
    ]

PARSERS = {
    Parser.DOCLING: _parse_with_docling,
    Parser.LITEPARSE: _parse_with_liteparse
}

def parse_document(parser: Parser, files: list[FileData]) -> list[ParsedFile]:
    try:
        parse = PARSERS[parser]
    except KeyError as exc:
        raise ValueError(f"Unsupported parser: {parser}") from exc
    return parse(files)
