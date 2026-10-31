"""Official-instruction ingestion with source provenance and scope-safe vector retrieval."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, url2pathname, urlopen
from uuid import UUID

from gradio import FileData
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from extraction.parse import parse_document
from schemas.common.enum import Parser

IRS_2025_PARTNER_INSTRUCTIONS_URL = "https://www.irs.gov/instructions/i1065sk1"
MANIFEST_VERSION = 1
DEFAULT_COLLECTION = "irs_schedule_k1_instructions"
DENSE_VECTOR = "dense"
BM25_VECTOR = "bm25"
DEFAULT_EMBED_MODEL = "lfm2.5-emb"
DEFAULT_EMBED_API_BASE = "http://192.168.8.10:8090/litellm"


@dataclass(frozen=True)
class InstructionScope:
    jurisdiction: str
    tax_year: int
    form_id: str
    revision: str | None
    audience: str


@dataclass(frozen=True)
class InstructionChunk:
    id: str
    text: str
    heading_path: tuple[str, ...]
    citation_locator: str
    scope: InstructionScope
    source_hash: str


@dataclass(frozen=True)
class RetrievalResult:
    needs_review: bool
    passages: tuple[InstructionChunk, ...]


class ConfiguredDenseEmbedder:
    """LiteLLM embedding client matching the repository's notebook configuration."""

    def __init__(self) -> None:
        configured_model = os.getenv("EMBED_MODEL", DEFAULT_EMBED_MODEL)
        self.model = (
            configured_model
            if "/" in configured_model
            else f"openai/{configured_model}"
        )
        self.api_base = os.getenv("EMBED_API_BASE", DEFAULT_EMBED_API_BASE)
        self.api_key = os.getenv("EMBED_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.extra_headers = json.loads(os.getenv("EMBED_EXTRA_HEADERS") or "{}")

    def _embed(self, texts: list[str]) -> list[list[float]]:
        from litellm import embedding

        kwargs = {
            "model": self.model,
            "api_base": self.api_base,
            "input": texts,
            "timeout": 600,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.extra_headers:
            kwargs["extra_headers"] = self.extra_headers
        response = embedding(**kwargs)
        return [
            item["embedding"]
            for item in sorted(response.data, key=lambda item: item["index"])
        ]

    def embed(self, texts):
        return iter(self._embed(list(texts)))

    def query_embed(self, text: str):
        return iter(self._embed([text]))


def download_instruction_source(
    url: str, destination: str | Path
) -> tuple[bytes, str, str]:
    """Retain an HTTP(S) or file:// instruction source and its detected format."""
    parsed = urlparse(url)
    if parsed.scheme == "file":
        if parsed.netloc not in {"", "localhost"}:
            raise ValueError(f"Unsupported file URL host: {parsed.netloc}")
        content = Path(url2pathname(parsed.path)).read_bytes()
        content_type = ""
    else:
        request = Request(url, headers={"User-Agent": "fde1-instruction-index/2"})
        with urlopen(request, timeout=30) as response:
            content = response.read()
            content_type = response.headers.get_content_type()
    source_format = (
        "pdf"
        if content_type == "application/pdf" or parsed.path.lower().endswith(".pdf")
        else "html"
    )
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return content, hashlib.sha256(content).hexdigest(), source_format


def download_irs_partner_instructions(destination: str | Path) -> tuple[bytes, str]:
    """Compatibility wrapper for the initial IRS HTML source."""
    content, source_hash, _ = download_instruction_source(
        IRS_2025_PARTNER_INSTRUCTIONS_URL, destination
    )
    return content, source_hash


def _make_chunk(
    source_hash: str,
    ordinal: int,
    locator: str,
    heading_path: tuple[str, ...],
    body: str,
    scope: InstructionScope,
) -> InstructionChunk:
    digest = hashlib.sha256(
        f"{source_hash}:{ordinal}:{locator}:{body}".encode()
    ).hexdigest()
    return InstructionChunk(
        str(UUID(hex=digest[:32])), body, heading_path, locator, scope, source_hash
    )


def chunk_instruction_source(
    content: bytes,
    source_path: str | Path,
    source_format: str,
    scope: InstructionScope,
    *,
    page_range: range | None = None,
) -> list[InstructionChunk]:
    """Chunk the shared Docling parse result with Docling's HybridChunker."""
    if source_format not in {"html", "pdf"}:
        raise ValueError(f"Unsupported instruction source format: {source_format}")
    from docling.chunking import HybridChunker

    path = Path(source_path)
    parsed = parse_document(
        [
            FileData(
                path=str(path),
                orig_name=path.name,
                mime_type="application/pdf" if source_format == "pdf" else "text/html",
                size=path.stat().st_size,
            )
        ],
        Parser.VLM,
    )
    if len(parsed) != 1:
        raise ValueError("Expected one parsed instruction source")
    document = parsed[0].result.document
    # Preserve each layout item (for example, individual form lines) as a
    # retrieval unit instead of merging peer items under the same heading.
    chunker = HybridChunker(repeat_table_header=True, merge_peers=False)
    source_hash = hashlib.sha256(content).hexdigest()
    chunks = []
    for ordinal, doc_chunk in enumerate(chunker.chunk(dl_doc=document)):
        pages = {
            provenance.page_no
            for item in doc_chunk.meta.doc_items
            for provenance in item.prov
        }
        if page_range is not None and not pages.issubset(page_range):
            continue
        text = chunker.contextualize(chunk=doc_chunk)
        meta = doc_chunk.meta
        heading_path = tuple(str(heading) for heading in (meta.headings or ()))
        refs = [item.self_ref for item in meta.doc_items]
        locator = ",".join(refs) or "document"
        chunks.append(
            _make_chunk(source_hash, ordinal, locator, heading_path, text, scope)
        )
    return chunks


def write_manifest(
    path: str | Path,
    *,
    source_url: str,
    downloaded_path: str | Path,
    source_hash: str,
    scope: InstructionScope,
    chunks: list[InstructionChunk],
    source_format: str = "html",
    page_range: range | None = None,
) -> None:
    manifest = {
        "version": MANIFEST_VERSION,
        "source_url": source_url,
        "downloaded_path": str(Path(downloaded_path)),
        "source_hash": source_hash,
        "source_format": source_format,
        "embedded_pages": (
            "all" if page_range is None else [page_range.start, page_range.stop - 1]
        ),
        "scope": asdict(scope),
        "chunks": [
            {
                "id": chunk.id,
                "heading_path": list(chunk.heading_path),
                "citation_locator": chunk.citation_locator,
            }
            for chunk in chunks
        ],
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


class InstructionIndex:
    """Scoped Qdrant index storing both FastEmbed dense and BM25 sparse vectors."""

    def __init__(
        self,
        client: QdrantClient,
        collection: str = DEFAULT_COLLECTION,
        *,
        dense_embedder=None,
        bm25_embedder=None,
    ) -> None:
        self.client, self.collection = client, collection
        self._dense_embedder, self._bm25_embedder = dense_embedder, bm25_embedder

    @classmethod
    def from_environment(
        cls, collection: str = DEFAULT_COLLECTION
    ) -> "InstructionIndex":
        return cls(
            QdrantClient(url=os.environ.get("QDRANT_URL", "http://localhost:6333")),
            collection,
        )

    def _dense(self):
        if self._dense_embedder is None:
            self._dense_embedder = ConfiguredDenseEmbedder()
        return self._dense_embedder

    def _bm25(self):
        if self._bm25_embedder is None:
            from fastembed import SparseTextEmbedding

            self._bm25_embedder = SparseTextEmbedding("Qdrant/bm25")
        return self._bm25_embedder

    def ensure_collection(self, dense_dimension: int) -> None:
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config={
                    DENSE_VECTOR: VectorParams(
                        size=dense_dimension, distance=Distance.COSINE
                    )
                },
                sparse_vectors_config={BM25_VECTOR: SparseVectorParams()},
            )

    @staticmethod
    def _sparse(vector) -> SparseVector:
        return SparseVector(indices=list(vector.indices), values=list(vector.values))

    def ingest(self, chunks: list[InstructionChunk]) -> int:
        if not chunks:
            return 0
        dense = list(self._dense().embed([chunk.text for chunk in chunks]))
        bm25 = list(self._bm25().embed([chunk.text for chunk in chunks]))
        if not dense:
            raise ValueError("Embedding provider returned no dense instruction vectors")
        self.ensure_collection(len(dense[0]))
        if len(dense) != len(chunks) or len(bm25) != len(chunks):
            raise ValueError(
                "Embedding provider returned an incomplete instruction batch"
            )
        points = [
            PointStruct(
                id=chunk.id,
                vector={
                    DENSE_VECTOR: list(dense[index]),
                    BM25_VECTOR: self._sparse(bm25[index]),
                },
                payload={
                    "text": chunk.text,
                    "jurisdiction": chunk.scope.jurisdiction,
                    "tax_year": chunk.scope.tax_year,
                    "form_id": chunk.scope.form_id,
                    "revision": chunk.scope.revision,
                    "audience": chunk.scope.audience,
                    "source_hash": chunk.source_hash,
                    "heading_path": list(chunk.heading_path),
                    "citation_locator": chunk.citation_locator,
                },
            )
            for index, chunk in enumerate(chunks)
        ]
        if points:
            self.client.upsert(
                collection_name=self.collection, points=points, wait=True
            )
        return len(points)

    @staticmethod
    def _filter(scope: InstructionScope) -> Filter:
        return Filter(
            must=[
                FieldCondition(key=key, match=MatchValue(value=value))
                for key, value in (
                    ("jurisdiction", scope.jurisdiction),
                    ("tax_year", scope.tax_year),
                    ("form_id", scope.form_id),
                    ("revision", scope.revision),
                    ("audience", scope.audience),
                )
            ]
        )

    def retrieve(
        self, query: str, scope: InstructionScope, limit: int = 5
    ) -> RetrievalResult:
        if not scope.revision:
            return RetrievalResult(needs_review=True, passages=())
        filter_ = self._filter(scope)
        dense_vector = list(next(self._dense().query_embed(query)))
        sparse_vector = self._sparse(next(self._bm25().query_embed(query)))
        dense = self.client.query_points(
            collection_name=self.collection,
            query=dense_vector,
            using=DENSE_VECTOR,
            query_filter=filter_,
            limit=limit * 4,
            with_payload=True,
        ).points
        sparse = self.client.query_points(
            collection_name=self.collection,
            query=sparse_vector,
            using=BM25_VECTOR,
            query_filter=filter_,
            limit=limit * 4,
            with_payload=True,
        ).points
        ranks: dict[str, tuple[object, float]] = {}
        for result_set in (dense, sparse):
            for rank, point in enumerate(result_set, 1):
                key = str(point.id)
                prior = ranks.get(key)
                ranks[key] = (point, (prior[1] if prior else 0.0) + 1 / (60 + rank))
        selected = sorted(ranks.values(), key=lambda item: (-item[1], str(item[0].id)))[
            :limit
        ]
        passages = tuple(
            InstructionChunk(
                id=str(point.id),
                text=point.payload["text"],
                heading_path=tuple(point.payload["heading_path"]),
                citation_locator=point.payload["citation_locator"],
                scope=scope,
                source_hash=point.payload["source_hash"],
            )
            for point, _ in selected
        )
        return RetrievalResult(needs_review=not passages, passages=passages)
