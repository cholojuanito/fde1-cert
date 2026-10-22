"""Normalize parser results into the application's extraction contract."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from uuid import uuid4

from config import config_from_env
from schemas.common.enum import (
    DocumentElementType,
    ExtractionArtifactFormat,
    ExtractionArtifactStatus,
    Parser,
)
from schemas.extraction.extraction import (
    BoundingBox,
    DocumentElement,
    ExtractedPage,
    ExtractionArtifact,
    SourceDocument,
    SourceLocation,
)


BIFROST_CONFIG = config_from_env()

def _plain(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "__dict__"):
        return {key: _plain(item) for key, item in vars(value).items() if not key.startswith("_")}
    return value


def _package_version(parser: Parser) -> str:
    package = "docling" if parser == Parser.DOCLING else "liteparse"
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"


def _source_document(path: str, filename: str, page_count: int) -> SourceDocument:
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return SourceDocument(
        id=digest,
        filename=filename,
        sha256=digest,
        page_count=page_count,
        storage_uri=Path(path).resolve().as_uri(),
    )


def _bbox_from_docling(raw: dict, page_height: float) -> BoundingBox:
    bbox = raw
    if bbox.get("coord_origin", "BOTTOMLEFT") == "BOTTOMLEFT":
        return BoundingBox(
            x0=bbox["l"], y0=page_height - bbox["t"],
            x1=bbox["r"], y1=page_height - bbox["b"],
        )
    return BoundingBox(x0=bbox["l"], y0=bbox["t"], x1=bbox["r"], y1=bbox["b"])


def _docling_pages(
    data: dict,
    artifact_id: str,
    ordered_refs: list[str] | None = None,
) -> tuple[list[ExtractedPage], list[str]]:
    document = data.get("document", {})
    raw_pages = document.get("pages", {})
    page_sizes = {
        int(page_no): details.get("size", {})
        for page_no, details in raw_pages.items()
    }
    elements_by_page: dict[int, list[DocumentElement]] = {
        page_no: [] for page_no in page_sizes
    }
    collections = (("texts", DocumentElementType.TEXT), ("tables", DocumentElementType.TABLE))
    records = []
    for collection_name, kind in collections:
        records.extend(
            (item.get("self_ref"), collection_name, index, item, kind)
            for index, item in enumerate(document.get(collection_name, []))
        )
    records_by_ref = {record[0]: record for record in records if record[0]}
    warnings = []
    if ordered_refs is not None:
        ordered_records = [records_by_ref[reference] for reference in ordered_refs if reference in records_by_ref]
        seen_refs = {record[0] for record in ordered_records}
        missing = [record for record in records if record[0] not in seen_refs]
        if missing:
            warnings.append(f"{len(missing)} Docling text/table items were absent from reading-order traversal")
        records = ordered_records + missing

    for _, collection_name, index, item, kind in records:
        provenance_items = item.get("prov", [])
        if not provenance_items:
            warnings.append(f"{item.get('self_ref', collection_name)} has no provenance and was skipped")
            continue
        for prov_index, provenance in enumerate(provenance_items):
            text = item.get("text")
            char_start = char_end = None
            if kind == DocumentElementType.TABLE:
                # Table provenance spans are not offsets into serialized table data.
                text = json.dumps(item.get("data", {}), ensure_ascii=False) or None
            elif len(provenance_items) > 1:
                charspan = provenance.get("charspan")
                original = item.get("orig")
                if not (
                    isinstance(original, str)
                    and isinstance(charspan, list)
                    and len(charspan) == 2
                    and isinstance(charspan[0], int)
                    and isinstance(charspan[1], int)
                    and 0 <= charspan[0] <= charspan[1] <= len(original)
                ):
                    warnings.append(
                        f"{item.get('self_ref', collection_name)} provenance {prov_index} has an invalid text span"
                    )
                    continue
                char_start, char_end = charspan
                text = original[char_start:char_end]
            else:
                charspan = provenance.get("charspan")
                if (
                    isinstance(charspan, list)
                    and len(charspan) == 2
                    and all(isinstance(value, int) for value in charspan)
                ):
                    char_start, char_end = charspan
            page_no = int(provenance.get("page_no", 1))
            page_height = page_sizes.get(page_no, {}).get("height", 0)
            raw_bbox = provenance.get("bbox")
            location = SourceLocation(
                page=page_no,
                bbox=_bbox_from_docling(raw_bbox, page_height) if raw_bbox and page_height else None,
                char_start=char_start,
                char_end=char_end,
            )
            elements_by_page.setdefault(page_no, []).append(
                DocumentElement(
                    id=f"{artifact_id}:{collection_name}:{index}:{prov_index}",
                    artifact_id=artifact_id,
                    kind=kind,
                    text=text,
                    locations=[location],
                    extractor_label=item.get("label"),
                    extractor_ref=item.get("self_ref"),
                )
            )

    return [
        ExtractedPage(
            artifact_id=artifact_id,
            page_number=page_no,
            width=dimensions.get("width", 1),
            height=dimensions.get("height", 1),
            elements=elements_by_page.get(page_no, []),
        )
        for page_no, dimensions in sorted(page_sizes.items())
    ], warnings


def _docling_reading_order_refs(result) -> list[str] | None:
    """Return source refs in Docling's tree order when a live document is available."""
    document = getattr(result, "document", None)
    if document is None or not hasattr(document, "iterate_items"):
        return None
    from docling_core.types.doc.common.content_layer import ContentLayer

    return [
        item.self_ref
        for item, _ in document.iterate_items(
            included_content_layers=set(ContentLayer),
            traverse_pictures=False,
        )
        if hasattr(item, "self_ref")
    ]


def _liteparse_pages(result, artifact_id: str) -> list[ExtractedPage]:
    pages = []
    for page in result.pages:
        elements = []
        for index, item in enumerate(page.text_items or []):
            x0, y0 = float(item.x), float(item.y)
            location = SourceLocation(
                page=int(page.page_num),
                bbox=BoundingBox(
                    x0=x0, y0=y0, x1=x0 + float(item.width), y1=y0 + float(item.height)
                ),
            )
            elements.append(
                DocumentElement(
                    id=f"{artifact_id}:text:{page.page_num}:{index}",
                    artifact_id=artifact_id,
                    kind=DocumentElementType.TEXT,
                    text=item.text,
                    locations=[location],
                    confidence=getattr(item, "confidence", None),
                    extractor_label="text_item",
                    extractor_ref=f"page:{page.page_num}:text:{index}",
                )
            )
        for index, block in enumerate(page.blocks or []):
            if block.kind != "table":
                continue
            bbox = block.bbox
            location = SourceLocation(
                page=int(page.page_num),
                bbox=BoundingBox(
                    x0=float(bbox.x), y0=float(bbox.y),
                    x1=float(bbox.x + bbox.width), y1=float(bbox.y + bbox.height),
                ) if bbox else None,
            )
            elements.append(
                DocumentElement(
                    id=f"{artifact_id}:table:{page.page_num}:{index}",
                    artifact_id=artifact_id,
                    kind=DocumentElementType.TABLE,
                    text=json.dumps(_plain(block), ensure_ascii=False),
                    locations=[location],
                    extractor_label="table",
                    extractor_ref=f"page:{page.page_num}:block:{index}",
                )
            )
        pages.append(
            ExtractedPage(
                artifact_id=artifact_id,
                page_number=int(page.page_num),
                width=float(page.width),
                height=float(page.height),
                elements=elements,
            )
        )
    return pages


class ExtractionArtifactAdapter(ABC):
    """Adapter interface: parser-specific results become ExtractionArtifact."""

    parser: Parser = BIFROST_CONFIG.parser

    @abstractmethod
    def adapt(self, parsed_file) -> ExtractionArtifact:
        """Translate one parser result into the application extraction model."""

    def _build_artifact(
        self,
        parsed_file,
        page_count: int,
        pages: list[ExtractedPage],
        status: ExtractionArtifactStatus,
        warnings: list[str],
    ) -> ExtractionArtifact:
        artifact_id = pages[0].artifact_id if pages else str(uuid4())
        source = _source_document(parsed_file.path, parsed_file.filename, page_count)
        return ExtractionArtifact(
            id=artifact_id,
            source_document=source,
            parser=self.parser,
            parser_version=_package_version(self.parser),
            config=BIFROST_CONFIG.parser_config[self.parser],
            status=status,
            format=ExtractionArtifactFormat.JSON,
            created_at=datetime.now(timezone.utc),
            pages=pages,
            warnings=warnings,
        )


class DoclingAdapter(ExtractionArtifactAdapter):
    """Adapt Docling ConversionResult objects to the shared artifact model."""

    parser = Parser.DOCLING

    def adapt(self, parsed_file) -> ExtractionArtifact:
        data = _plain(parsed_file.result)
        page_count = int(data.get("input", {}).get("page_count", 0))
        artifact_id = str(uuid4())
        pages, adaptation_warnings = _docling_pages(
            data,
            artifact_id,
            _docling_reading_order_refs(parsed_file.result),
        )
        errors = data.get("errors", [])
        status_value = str(data.get("status", "success")).lower()
        status = (
            ExtractionArtifactStatus.FAILED if status_value in {"failure", "failed"}
            else ExtractionArtifactStatus.PARTIAL if errors or len(pages) < page_count
            else ExtractionArtifactStatus.COMPLETED
        )
        warnings = [str(error.get("error_message", error)) for error in errors] + adaptation_warnings
        return self._build_artifact(parsed_file, page_count, pages, status, warnings)


class LiteParseAdapter(ExtractionArtifactAdapter):
    """Adapt LiteParse ParseResult objects to the shared artifact model."""

    parser = Parser.LITEPARSE

    def adapt(self, parsed_file) -> ExtractionArtifact:
        result = parsed_file.result
        page_count = int(result.total_pages)
        artifact_id = str(uuid4())
        pages = _liteparse_pages(result, artifact_id)
        warnings = [str(error) for error in (result.page_errors or [])]
        status = (
            ExtractionArtifactStatus.PARTIAL if warnings or len(pages) < page_count
            else ExtractionArtifactStatus.COMPLETED
        )
        return self._build_artifact(parsed_file, page_count, pages, status, warnings)


_ADAPTERS: dict[Parser, type[ExtractionArtifactAdapter]] = {
    Parser.DOCLING: DoclingAdapter,
    Parser.LITEPARSE: LiteParseAdapter,
}


def adapter_for(parser: Parser) -> ExtractionArtifactAdapter:
    """Return the concrete adapter for a parser implementation."""
    try:
        return _ADAPTERS[parser]()
    except KeyError as exc:
        raise ValueError(f"No extraction artifact adapter for parser {parser}") from exc
