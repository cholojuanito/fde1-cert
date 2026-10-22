
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
    """Bifrost specific configurations"""
    parser: Parser
    parser_config: dict[Parser,dict]

def _docling_config() -> dict:
    return {
        "do_ocr": env_bool("DOCLING_DO_OCR", False),
        "ocr_mode": os.getenv("DOCLING_OCR_MODE", "full_page"),
        "do_table_structure": env_bool("DOCLING_DO_TABLE_STRUCTURE", False)
    }

def _liteparse_config() -> dict:
    return {
        "ocr_enabled": env_bool("LITEPARSE_OCR_ENABLED", False),
        "extract_blocks": env_bool("LITEPARSE_EXTRACT_BLOCKS", False)
    }

def config_from_env() -> Config:
    parser_config = {
        Parser.DOCLING: _docling_config(),
        Parser.LITEPARSE: _liteparse_config(),
    }
    return Config(
        parser=Parser(os.getenv("EXTRACTION_PARSER", Parser.DOCLING.value)),
        parser_config=parser_config
    )
