from dataclasses import dataclass
from gradio import FileData

from schemas.common.enum import Parser
from config import config_from_env

PARSER_CONFIG = config_from_env()

@dataclass
class ParsedFile:
    filename: str
    path: str
    result: object


def _parse_with_docling(files: list[FileData]) -> list[ParsedFile]:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = PARSER_CONFIG.get("do_ocr")
    pipeline_options.ocr_options.mode = PARSER_CONFIG.get("ocr_mode")
    pipeline_options.do_table_structure = PARSER_CONFIG.get("do_table_structure")
    pipeline_options.table_structure_options = TableStructureOptions(do_cell_matching= PARSER_CONFIG.get("do_cell_matching"))
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
    )
    return [
        ParsedFile(file.orig_name, file.path, converter.convert(file.path))
        for file in files
    ]

def _parse_with_vlm(files: list[FileData]) -> list[ParsedFile]:
    """Convert pages locally with Docling's VLM pipeline."""
    from docling.datamodel import vlm_model_specs
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import VlmPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.pipeline.vlm_pipeline import VlmPipeline

    preset = PARSER_CONFIG.parser_config[Parser.VLM]["preset"]
    preset_names = {
        "granite_docling": "GRANITEDOCLING_TRANSFORMERS",
        "granite_docling_vllm": "GRANITEDOCLING_VLLM",
    }
    try:
        vlm_options = getattr(vlm_model_specs, preset_names.get(preset, preset.upper()))
    except AttributeError as exc:
        raise ValueError(
            f"Installed Docling does not expose requested VLM preset {preset!r}"
        ) from exc
    options = VlmPipelineOptions(
        vlm_options=vlm_options,
        generate_page_images=PARSER_CONFIG.parser_config[Parser.VLM][
            "generate_page_images"
        ],
    )
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_cls=VlmPipeline, pipeline_options=options
            )
        }
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
    Parser.VLM: _parse_with_vlm,
    Parser.LITEPARSE: _parse_with_liteparse,
}


def parse_document(files: list[FileData], parser: Parser | None = None) -> list[ParsedFile]:
    active_parser = parser or PARSER_CONFIG.parser
    try:
        parse = PARSERS[active_parser]
    except KeyError as exc:
        raise ValueError(f"Unsupported parser: {parser}") from exc
    return parse(files)
