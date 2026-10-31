import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from extraction.instructions import (
    BM25_VECTOR,
    DENSE_VECTOR,
    InstructionIndex,
    InstructionScope,
    _make_chunk,
    chunk_instruction_source,
    download_instruction_source,
    write_manifest,
)

HTML = b"""
<h1 id='top'>Partner's Instructions</h1>
<h2 id='box13'>Box 13. Other Deductions</h2>
<p>Code W reports other deductions for partners.</p>
<h2 id='box14'>Box 14. Self-Employment Earnings</h2>
<p>Code W reports self-employment earnings when applicable.</p>
"""


class Dense:
    def embed(self, texts):
        return ([float(len(text)), 1.0] for text in texts)

    def query_embed(self, text):
        return iter(([float(len(text)), 1.0],))


class Sparse:
    def embed(self, texts):
        return (
            SimpleNamespace(indices=[index], values=[1.0])
            for index, _ in enumerate(texts)
        )

    def query_embed(self, text):
        return iter((SimpleNamespace(indices=[0], values=[1.0]),))


class FakeQdrant:
    def __init__(self):
        self.collections = set()
        self.points = {}
        self.collection_config = None

    def collection_exists(self, collection_name):
        return collection_name in self.collections

    def create_collection(self, collection_name, vectors_config, sparse_vectors_config):
        self.collections.add(collection_name)
        self.collection_config = vectors_config, sparse_vectors_config

    def upsert(self, collection_name, points, wait):
        self.points.setdefault(collection_name, {})
        for point in points:
            self.points[collection_name][str(point.id)] = point

    def query_points(
        self, collection_name, query, using, query_filter, limit, with_payload
    ):
        required = {
            condition.key: condition.match.value for condition in query_filter.must
        }
        points = [
            SimpleNamespace(id=point.id, payload=point.payload)
            for point in self.points.get(collection_name, {}).values()
            if all(point.payload.get(key) == value for key, value in required.items())
        ]
        return SimpleNamespace(points=points[:limit])


class InstructionIndexTests(unittest.TestCase):
    def setUp(self):
        self.scope = InstructionScope(
            "federal", 2025, "1065-schedule-k-1", "2025", "partner"
        )
        self.client = FakeQdrant()
        self.index = InstructionIndex(
            self.client, "test", dense_embedder=Dense(), bm25_embedder=Sparse()
        )
        self.chunks = [
            _make_chunk(
                "source",
                0,
                "#/texts/1",
                ("Box 13",),
                "Box 13. Other Deductions\nCode W reports other deductions.",
                self.scope,
            ),
            _make_chunk(
                "source",
                1,
                "#/texts/2",
                ("Box 14",),
                "Box 14. Self-Employment Earnings\nCode W applies.",
                self.scope,
            ),
        ]

    def test_ingest_stores_dense_and_bm25_vectors_with_provenance(self):
        self.assertEqual(self.index.ingest(self.chunks), 2)
        vectors, sparse = self.client.collection_config
        self.assertIn(DENSE_VECTOR, vectors)
        self.assertIn(BM25_VECTOR, sparse)
        point = next(iter(self.client.points["test"].values()))
        self.assertIn(DENSE_VECTOR, point.vector)
        self.assertIn(BM25_VECTOR, point.vector)
        self.assertEqual(point.payload["source_hash"], self.chunks[0].source_hash)

    def test_retrieval_filters_scope_before_vector_search(self):
        self.index.ingest(self.chunks)
        result = self.index.retrieve("Box 13 Code W", self.scope)
        self.assertFalse(result.needs_review)
        self.assertIn("Box 13", result.passages[0].text)
        wrong_year = self.index.retrieve(
            "Box 13 Code W",
            InstructionScope("federal", 2024, "1065-schedule-k-1", "2025", "partner"),
        )
        self.assertTrue(wrong_year.needs_review)
        self.assertEqual(wrong_year.passages, ())
        unknown_revision = self.index.retrieve(
            "Box 13",
            InstructionScope("federal", 2025, "1065-schedule-k-1", None, "partner"),
        )
        self.assertTrue(unknown_revision.needs_review)

    def test_file_url_source_is_copied_with_pdf_format(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "instructions.pdf"
            destination = Path(directory) / "ingested.pdf"
            source.write_bytes(b"local-pdf")
            content, source_hash, source_format = download_instruction_source(
                source.as_uri(), destination
            )
            stored = destination.read_bytes()
        self.assertEqual(content, b"local-pdf")
        self.assertEqual(source_format, "pdf")
        self.assertEqual(source_hash, hashlib.sha256(b"local-pdf").hexdigest())
        self.assertEqual(stored, b"local-pdf")

    def test_pdf_chunking_uses_docling_hybrid_chunker(self):
        doc_item = SimpleNamespace(
            self_ref="#/tables/1", prov=[SimpleNamespace(page_no=1)]
        )
        doc_chunk = SimpleNamespace(
            meta=SimpleNamespace(
                headings=["Partner Instructions", "Box 13"], doc_items=[doc_item]
            )
        )
        unheaded_chunk = SimpleNamespace(
            meta=SimpleNamespace(headings=None, doc_items=[doc_item])
        )

        class Converter:
            def convert(self, path):
                return SimpleNamespace(document=object())

        class Chunker:
            def __init__(self, repeat_table_header, merge_peers):
                self.repeat_table_header = repeat_table_header
                self.merge_peers = merge_peers

            def chunk(self, *, dl_doc):
                return iter([doc_chunk, unheaded_chunk])

            def contextualize(self, *, chunk):
                return "Table header\nCode W deduction"

        with (
            tempfile.NamedTemporaryFile(suffix=".pdf") as source,
            patch(
                "docling.document_converter.DocumentConverter", return_value=Converter()
            ),
            patch(
                "docling.chunking.HybridChunker",
                return_value=Chunker(True, False),
            ) as chunker_factory,
        ):
            source.write(b"pdf")
            source.flush()
            chunks = chunk_instruction_source(b"pdf", source.name, "pdf", self.scope)
            included = chunk_instruction_source(
                b"pdf", source.name, "pdf", self.scope, page_range=range(1, 2)
            )
            excluded = chunk_instruction_source(
                b"pdf", source.name, "pdf", self.scope, page_range=range(2, 3)
            )
        self.assertEqual(chunker_factory.call_count, 3)
        self.assertEqual(included, chunks)
        self.assertEqual(excluded, [])
        self.assertEqual(chunks[0].heading_path, ("Partner Instructions", "Box 13"))
        self.assertEqual(chunks[1].heading_path, ())
        self.assertIn("Table header", chunks[0].text)

    def test_manifest_records_source_format(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            write_manifest(
                path,
                source_url="https://example.test/instructions.pdf",
                downloaded_path="source.pdf",
                source_hash="hash",
                source_format="pdf",
                scope=self.scope,
                chunks=self.chunks,
            )
            manifest = json.loads(path.read_text())
        self.assertEqual(manifest["source_format"], "pdf")
        self.assertEqual(manifest["embedded_pages"], "all")

    def test_unknown_format_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            chunk_instruction_source(b"x", "source", "docx", self.scope)


if __name__ == "__main__":
    unittest.main()
