#!/usr/bin/env python3
"""Ingest or query the official IRS 2025 Schedule K-1 partner instructions."""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extraction.instructions import (
    IRS_2025_PARTNER_INSTRUCTIONS_URL,
    InstructionIndex,
    InstructionScope,
    chunk_instruction_source,
    download_instruction_source,
    write_manifest,
)


def _scope(args: argparse.Namespace) -> InstructionScope:
    return InstructionScope(
        jurisdiction=args.jurisdiction,
        tax_year=args.tax_year,
        form_id=args.form_id,
        revision=args.revision,
        audience=args.audience,
    )


def _page_range(value: str) -> range:
    try:
        first, last = (int(page) for page in value.split("-", 1))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "pages must be START-END, for example 2-4"
        ) from exc
    if first < 1 or last < first:
        raise argparse.ArgumentTypeError(
            "pages are 1-based and START must not exceed END"
        )
    return range(first, last + 1)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("ingest", "query"))
    parser.add_argument("--jurisdiction", default="federal")
    parser.add_argument("--tax-year", type=int, default=2025)
    parser.add_argument("--form-id", default="1065-schedule-k-1")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--audience", default="partner")
    parser.add_argument("--collection", default="irs_schedule_k1_instructions")
    parser.add_argument("--query")
    parser.add_argument("--url", default=IRS_2025_PARTNER_INSTRUCTIONS_URL)
    parser.add_argument("--data-dir", type=Path, default=Path(".instruction-index"))
    parser.add_argument(
        "--pages",
        type=_page_range,
        metavar="START-END",
        help="Embed only this inclusive Docling page range (Docling pages are 1-based).",
    )
    args = parser.parse_args()
    scope = _scope(args)
    index = InstructionIndex.from_environment(args.collection)

    if args.action == "query":
        if not args.query:
            parser.error("--query is required for query")
        result = index.retrieve(args.query, scope)
        print(
            {
                "needs_review": result.needs_review,
                "passages": [passage.__dict__ for passage in result.passages],
            }
        )
        return

    suffix = ".pdf" if args.url.lower().split("?", 1)[0].endswith(".pdf") else ".html"
    source_path = args.data_dir / f"instructions{suffix}"
    manifest_path = args.data_dir / "instructions.manifest.json"
    content, source_hash, source_format = download_instruction_source(
        args.url, source_path
    )
    chunks = chunk_instruction_source(
        content, source_path, source_format, scope, page_range=args.pages
    )
    indexed = index.ingest(chunks)
    write_manifest(
        manifest_path,
        source_url=args.url,
        downloaded_path=source_path,
        source_hash=source_hash,
        source_format=source_format,
        scope=scope,
        chunks=chunks,
        page_range=args.pages,
    )
    print(
        {
            "indexed": indexed,
            "source_hash": source_hash,
            "source_format": source_format,
            "manifest": str(manifest_path),
        }
    )


if __name__ == "__main__":
    main()
