import tempfile
import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gradio import FileData

from extraction.adapters import (
    DoclingAdapter,
    LiteParseAdapter,
    _docling_pages,
    adapter_for,
)
from extraction.inspect import inspect_document
from extraction.parse import ParsedFile, parse_document
from llm import extract_tax_fields
from schema import Request, solve
from schemas.common.enum import (
    ExtractionArtifactStatus,
    ObservationStatus,
    Parser,
    ReviewStatus,
    TaxReturnType,
)
from schemas.domain.forms.factory import (
    FormIdentity,
    create_form_definition,
    identify_artifact_form,
    require_readable_fields,
)
from schemas.domain.tax_document import FieldExtractionDraft, TaxExtractionDraft
from schemas.common.types import MoneyValue, PercentageValue, TextValue


DATA_DIR = Path(__file__).resolve().parents[3] / "use_case" / "data"
SAMPLE_PDF = DATA_DIR / "2025-utah-tc-65-k1.pdf"


def docling_result(text="A Partnership's EIN:", extra_texts=()):
    texts = [
        {
            "self_ref": "#/texts/0",
            "label": "section_header",
            "text": "Schedule K-1 - TC-65, Sch. K-1 2025",
            "prov": [
                {
                    "page_no": 1,
                    "bbox": {
                        "l": 10.0,
                        "t": 100.0,
                        "r": 100.0,
                        "b": 90.0,
                        "coord_origin": "BOTTOMLEFT",
                    },
                    "charspan": [0, 38],
                }
            ],
        },
        {
            "self_ref": "#/texts/1",
            "label": "text",
            "text": text,
            "prov": [
                {
                    "page_no": 1,
                    "bbox": {
                        "l": 10.0,
                        "t": 100.0,
                        "r": 100.0,
                        "b": 90.0,
                        "coord_origin": "BOTTOMLEFT",
                    },
                    "charspan": [0, len(text)],
                }
            ],
        },
    ]
    for index, value in enumerate(extra_texts, start=2):
        texts.append(
            {
                "self_ref": f"#/texts/{index}",
                "label": "text",
                "text": value,
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 10.0,
                            "t": 100.0,
                            "r": 100.0,
                            "b": 90.0,
                            "coord_origin": "BOTTOMLEFT",
                        },
                        "charspan": [0, len(value)],
                    }
                ],
            }
        )
    return {
        "status": "success",
        "errors": [],
        "input": {"page_count": 1},
        "document": {
            "pages": {"1": {"size": {"width": 612.0, "height": 792.0}}},
            "texts": texts,
            "tables": [],
        },
    }


class AdapterUnitTests(unittest.TestCase):
    def test_docling_result_becomes_artifact_with_normalized_coordinates(self):
        with tempfile.NamedTemporaryFile() as source:
            Path(source.name).write_bytes(b"pdf bytes")
            parsed = ParsedFile("sample.pdf", source.name, docling_result())
            artifact = DoclingAdapter().adapt(parsed)

        self.assertEqual(artifact.status, ExtractionArtifactStatus.COMPLETED)
        self.assertEqual(artifact.source_document.page_count, 1)
        self.assertEqual(len(artifact.pages), 1)
        element = artifact.pages[0].elements[1]
        self.assertEqual(element.text, "A Partnership's EIN:")
        self.assertEqual(element.locations[0].bbox.y0, 692.0)
        self.assertEqual(element.locations[0].bbox.y1, 702.0)
        self.assertEqual(element.artifact_id, artifact.id)

    def test_liteparse_result_becomes_artifact(self):
        text_item = SimpleNamespace(
            text="line 1", x=10, y=20, width=30, height=8, confidence=0.9
        )
        page = SimpleNamespace(
            page_num=1,
            width=612,
            height=792,
            text_items=[text_item],
            blocks=[],
        )
        result = SimpleNamespace(total_pages=1, pages=[page], page_errors=[])
        with tempfile.NamedTemporaryFile() as source:
            Path(source.name).write_bytes(b"pdf bytes")
            artifact = LiteParseAdapter().adapt(
                ParsedFile("sample.pdf", source.name, result)
            )

        self.assertEqual(artifact.status, ExtractionArtifactStatus.COMPLETED)
        self.assertEqual(artifact.pages[0].elements[0].text, "line 1")
        self.assertEqual(artifact.pages[0].elements[0].locations[0].bbox.x1, 40)

    def test_docling_multi_provenance_uses_original_text_fragments(self):
        result = docling_result()
        result["document"]["texts"].append(
            {
                "self_ref": "#/texts/2",
                "label": "text",
                "orig": "Alpha Beta",
                "text": "AlphaBeta",
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 10,
                            "t": 100,
                            "r": 40,
                            "b": 90,
                            "coord_origin": "BOTTOMLEFT",
                        },
                        "charspan": [0, 5],
                    },
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 50,
                            "t": 100,
                            "r": 80,
                            "b": 90,
                            "coord_origin": "BOTTOMLEFT",
                        },
                        "charspan": [6, 10],
                    },
                ],
            }
        )
        with tempfile.NamedTemporaryFile() as source:
            Path(source.name).write_bytes(b"pdf bytes")
            artifact = DoclingAdapter().adapt(
                ParsedFile("sample.pdf", source.name, result)
            )

        fragments = [
            element
            for element in artifact.pages[0].elements
            if element.extractor_ref == "#/texts/2"
        ]
        self.assertEqual([element.text for element in fragments], ["Alpha", "Beta"])
        self.assertEqual(
            [element.locations[0].char_start for element in fragments], [0, 6]
        )

    def test_docling_invalid_multi_provenance_retains_source_text(self):
        result = docling_result()
        result["document"]["texts"].append(
            {
                "self_ref": "#/texts/2",
                "label": "text",
                "orig": "Alpha Beta",
                "text": "AlphaBeta",
                "prov": [
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 10,
                            "t": 100,
                            "r": 40,
                            "b": 90,
                            "coord_origin": "BOTTOMLEFT",
                        },
                        "charspan": [0, 5],
                    },
                    {
                        "page_no": 1,
                        "bbox": {
                            "l": 50,
                            "t": 100,
                            "r": 80,
                            "b": 90,
                            "coord_origin": "BOTTOMLEFT",
                        },
                        "charspan": [99, 100],
                    },
                ],
            }
        )
        with tempfile.NamedTemporaryFile() as source:
            Path(source.name).write_bytes(b"pdf bytes")
            artifact = DoclingAdapter().adapt(
                ParsedFile("sample.pdf", source.name, result)
            )

        fragments = [
            element
            for element in artifact.pages[0].elements
            if element.extractor_ref == "#/texts/2"
        ]
        self.assertEqual(
            [element.text for element in fragments], ["Alpha", "AlphaBeta"]
        )
        self.assertIsNone(fragments[1].locations[0].char_start)
        self.assertTrue(
            any("retaining unsplit" in warning for warning in artifact.warnings)
        )

    def test_docling_pages_follow_supplied_reading_order(self):
        pages, warnings = _docling_pages(
            docling_result(),
            "artifact",
            ["#/texts/1", "#/texts/0"],
        )

        self.assertFalse(warnings)
        self.assertEqual(
            [element.extractor_ref for element in pages[0].elements],
            ["#/texts/1", "#/texts/0"],
        )

    def test_structured_llm_call_is_single_and_validated(self):
        definition = create_form_definition(
            FormIdentity(
                return_type=TaxReturnType.UTAH_TC65,
                tax_year=2025,
                schedule="K-1",
            )
        )
        with tempfile.NamedTemporaryFile() as source:
            Path(source.name).write_bytes(b"pdf bytes")
            artifact = adapter_for(Parser.DOCLING).adapt(
                ParsedFile("sample.pdf", source.name, docling_result())
            )
        payload = TaxExtractionDraft(
            form_id=definition.form_id,
            tax_year=2025,
            fields=[
                FieldExtractionDraft(
                    field_id=definition.fields[0].id,
                    observation_status=ObservationStatus.BLANK,
                    reason="Form value is blank",
                )
            ],
        ).model_dump_json()
        completion_result = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=payload))]
        )
        with patch("llm.completion", return_value=completion_result) as completion:
            draft = extract_tax_fields(artifact, definition)

        self.assertEqual(draft.tax_year, 2025)
        self.assertEqual(completion.call_count, 1)
        self.assertEqual(
            completion.call_args.kwargs["response_format"], {"type": "json_object"}
        )
        self.assertFalse(completion.call_args.kwargs["stream"])
        prompt = json.loads(completion.call_args.kwargs["messages"][1]["content"])
        evidence = prompt["document"]["evidence"]
        self.assertIn(
            f"[{artifact.pages[0].elements[1].id}] p1 (10,692)-(100,702)", evidence
        )
        self.assertIn("A Partnership's EIN:", evidence)
        self.assertNotIn("elements", prompt["document"])
        hint = next(
            item
            for item in prompt["document"]["field_hints"]
            if item["field_id"] == "entity.ein"
        )
        self.assertIn(artifact.pages[0].elements[1].id, hint["nearby_evidence"][0])

    def test_inspection_writes_raw_artifact_and_production_prompt(self):
        raw_document = docling_result(extra_texts=["Percent of ownership"])["document"]

        class Document:
            def model_dump(self, mode):
                return raw_document

        class Result:
            document = Document()

            def model_dump(self, mode):
                return {
                    "status": "success",
                    "errors": [],
                    "input": {"page_count": 1},
                    "document": raw_document,
                }

        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "fixture.pdf"
            pdf.write_bytes(b"pdf bytes")
            output = Path(directory) / "inspection"
            with patch(
                "extraction.inspect.parse_document",
                return_value=[ParsedFile("fixture.pdf", str(pdf), Result())],
            ):
                summary = inspect_document(pdf, output)

            self.assertEqual(summary["elements"], 3)
            self.assertTrue((output / "docling-document.json").exists())
            self.assertTrue((output / "extraction-artifact.json").exists())
            prompt = json.loads((output / "extraction-prompt.json").read_text())
            self.assertIn("evidence", prompt["messages"][1]["content"])


@unittest.skipUnless(SAMPLE_PDF.exists(), "2025 Utah K-1 sample PDF not available")
class ParserIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.file_data = FileData(
            path=str(SAMPLE_PDF),
            orig_name=SAMPLE_PDF.name,
            mime_type="application/pdf",
            size=SAMPLE_PDF.stat().st_size,
        )

    def test_docling_parse_converts_to_extraction_artifact(self):
        parsed_files = parse_document([self.file_data], Parser.DOCLING)
        artifact = adapter_for(Parser.DOCLING).adapt(parsed_files[0])

        self.assertEqual(artifact.parser, Parser.DOCLING)
        self.assertEqual(artifact.source_document.sha256, artifact.source_document.id)
        self.assertEqual(artifact.source_document.page_count, 1)
        self.assertTrue(artifact.config["do_ocr"])
        self.assertEqual(artifact.config["ocr_mode"], "full_page")
        self.assertTrue(artifact.pages)
        self.assertTrue(
            any(element.text for page in artifact.pages for element in page.elements)
        )
        identity = identify_artifact_form(artifact)
        self.assertEqual(identity.return_type, TaxReturnType.UTAH_TC65)
        self.assertEqual(identity.tax_year, 2025)
        self.assertEqual(identity.page_numbers, [1])
        require_readable_fields(
            artifact,
            create_form_definition(identity),
            identity.page_numbers,
        )

    def test_liteparse_parse_converts_to_extraction_artifact(self):
        parsed_files = parse_document([self.file_data], Parser.LITEPARSE)
        artifact = adapter_for(Parser.LITEPARSE).adapt(parsed_files[0])

        self.assertEqual(artifact.parser, Parser.LITEPARSE)
        self.assertEqual(artifact.source_document.page_count, 1)
        self.assertEqual(len(artifact.pages), 1)


if __name__ == "__main__":
    unittest.main()
