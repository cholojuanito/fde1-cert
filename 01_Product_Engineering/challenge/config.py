import os
from dataclasses import dataclass
from schemas.common.enum import Parser


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    if value.casefold() in {"true", "1", "yes"}:
        return True
    if value.casefold() in {"false", "0", "no"}:
        return False
    raise ValueError(f"{name} must be true or false")


@dataclass(frozen=True)
class Config:
    """Parser configuration selected from the environment."""

    parser: Parser
    parser_config: dict[Parser, dict]

    def get(self, key: str, default=None):
        return self.parser_config.get(self.parser, {}).get(key, default)


def _docling_config() -> dict:
    return {
        "do_ocr": env_bool("DOCLING_DO_OCR", True),
        "ocr_mode": os.getenv("DOCLING_OCR_MODE", "full_page"),
        "do_table_structure": env_bool("DOCLING_DO_TABLE_STRUCTURE", True),
        "do_cell_matching": env_bool("DOCLING_TABLE_DO_CELL_MATCHING", True),
        "generate_page_images": env_bool("DOCLING_GEN_PAGE_IMAGES", True),
    }


def _vlm_config() -> dict:
    return {
        "preset": os.getenv("DOCLING_VLM_PRESET", "granite_docling"),
        "generate_page_images": env_bool("DOCLING_VLM_GENERATE_PAGE_IMAGES", False),
    }


def _liteparse_config() -> dict:
    return {
        "ocr_enabled": env_bool("LITEPARSE_OCR_ENABLED", False),
        "extract_blocks": env_bool("LITEPARSE_EXTRACT_BLOCKS", False),
    }


def config_from_env() -> Config:
    parser_config = {
        Parser.DOCLING: _docling_config(),
        Parser.VLM: _vlm_config(),
        Parser.LITEPARSE: _liteparse_config(),
    }
    return Config(
        parser=Parser(os.getenv("EXTRACTION_PARSER", Parser.DOCLING.value)),
        parser_config=parser_config,
    )
