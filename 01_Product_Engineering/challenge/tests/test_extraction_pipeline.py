import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from gradio import FileData

from extraction.adapters import DoclingAdapter, LiteParseAdapter, adapter_for
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


DATA_DIR = Path(__file__).resolve().parents[3] / "use_case" / "data"
SAMPLE_PDF = DATA_DIR / "2025-utah-tc-65-k1.pdf"


def docling_result(text="A Partnership's EIN:", extra_texts=()):
    texts = [
        {
            "self_ref": "#/texts/0", "label": "section_header",
            "text": "Schedule K-1 - TC-65, Sch. K-1 2025",
            "prov": [{"page_no": 1, "bbox": {"l": 10.0, "t": 100.0, "r": 100.0, "b": 90.0, "coord_origin": "BOTTOMLEFT"}, "charspan": [0, 38]}],
        },
        {
            "self_ref": "#/texts/1", "label": "text", "text": text,
            "prov": [{"page_no": 1, "bbox": {"l": 10.0, "t": 100.0, "r": 100.0, "b": 90.0, "coord_origin": "BOTTOMLEFT"}, "charspan": [0, len(text)]}],
        },
    ]
    for index, value in enumerate(extra_texts, start=2):
        texts.append({
            "self_ref": f"#/texts/{index}", "label": "text", "text": value,
            "prov": [{"page_no": 1, "bbox": {"l": 10.0, "t": 100.0, "r": 100.0, "b": 90.0, "coord_origin": "BOTTOMLEFT"}, "charspan": [0, len(value)]}],
        })
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
        text_item = SimpleNamespace(text="line 1", x=10, y=20, width=30, height=8, confidence=0.9)
        page = SimpleNamespace(
            page_num=1, width=612, height=792, text_items=[text_item], blocks=[],
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

    def test_structured_llm_call_is_single_and_validated(self):
        definition = create_form_definition(FormIdentity(
            return_type=TaxReturnType.UTAH_TC65,
            tax_year=2025,
            schedule="K-1",
        ))
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
        self.assertIs(completion.call_args.kwargs["response_format"], TaxExtractionDraft)
        self.assertFalse(completion.call_args.kwargs["stream"])


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
        parsed_files = parse_document(Parser.DOCLING, [self.file_data])
        artifact = adapter_for(Parser.DOCLING).adapt(parsed_files[0])

        self.assertEqual(artifact.parser, Parser.DOCLING)
        self.assertEqual(artifact.source_document.sha256, artifact.source_document.id)
        self.assertEqual(artifact.source_document.page_count, 1)
        self.assertTrue(artifact.config["do_ocr"])
        self.assertEqual(artifact.config["ocr_mode"], "full_page")
        self.assertTrue(artifact.pages)
        self.assertTrue(any(element.text for page in artifact.pages for element in page.elements))
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
        parsed_files = parse_document(Parser.LITEPARSE, [self.file_data])
        artifact = adapter_for(Parser.LITEPARSE).adapt(parsed_files[0])

        self.assertEqual(artifact.parser, Parser.LITEPARSE)
        self.assertEqual(artifact.source_document.page_count, 1)
        self.assertEqual(len(artifact.pages), 1)


class PipelineEndToEndTests(unittest.TestCase):
    def test_request_rejects_multiple_pdfs(self):
        with self.assertRaises(ValueError):
            Request(files=[
                FileData(path="one.pdf", orig_name="one.pdf", mime_type="application/pdf", size=1),
                FileData(path="two.pdf", orig_name="two.pdf", mime_type="application/pdf", size=1),
            ])

    def test_solve_returns_typed_observations_and_resolved_evidence(self):
        with tempfile.NamedTemporaryFile() as source:
            Path(source.name).write_bytes(b"fixture pdf")
            definition = create_form_definition(FormIdentity(
                return_type=TaxReturnType.UTAH_TC65,
                tax_year=2025,
                schedule="K-1",
            ))
            label_texts = [field.source.labels[0] for field in definition.fields]
            parsed = ParsedFile(
                "fixture.pdf",
                source.name,
                docling_result(extra_texts=label_texts),
            )
            selected_pages = None
            evidence_ids = []

            def fake_extract(artifact, definition, page_numbers=None):
                nonlocal selected_pages, evidence_ids
                selected_pages = page_numbers
                elements = artifact.pages[0].elements
                evidence_ids = [element.id for element in elements[2:]]
                return TaxExtractionDraft(
                    form_id=definition.form_id,
                    tax_year=definition.tax_year,
                    fields=[
                        FieldExtractionDraft(
                            field_id=field.id,
                            observation_status=ObservationStatus.BLANK,
                            evidence_element_ids=[] if index == 0 else [evidence_ids[index]],
                        )
                        for index, field in enumerate(definition.fields)
                    ],
                )

            request = Request(files=[FileData(
                path=source.name,
                orig_name="fixture.pdf",
                mime_type="application/pdf",
                size=11,
            )])
            with patch("schema.parse_document", return_value=[parsed]), patch(
                "schema.extract_tax_fields", side_effect=fake_extract
            ):
                response = solve(request)

        self.assertEqual(len(response.document.fields), len(definition.fields))
        self.assertEqual(response.document.fields[0].observation_status, ObservationStatus.BLANK)
        self.assertEqual(response.document.fields[0].status, ReviewStatus.NEEDS_REVIEW)
        self.assertFalse(response.document.fields[0].evidence)
        self.assertEqual(response.document.fields[1].evidence[0].element_id, evidence_ids[1])
        self.assertEqual(len({field.evidence[0].element_id for field in response.document.fields[1:]}), len(definition.fields) - 1)
        self.assertEqual(response.document.form_revision, "2025-original")
        self.assertEqual(response.audit_result.tax_year, 2025)
        self.assertEqual(selected_pages, [1])
        self.assertFalse(response.audit_result.export_ready)

    def test_unsupported_form_is_rejected_before_model_call(self):
        with tempfile.NamedTemporaryFile() as source:
            Path(source.name).write_bytes(b"fixture pdf")
            other_form = docling_result("A label")
            other_form["document"]["texts"][0]["text"] = "Utah Corporation Franchise and Income Tax Return TC-20 2025"
            parsed = ParsedFile("other.pdf", source.name, other_form)
            request = Request(files=[FileData(
                path=source.name,
                orig_name="other.pdf",
                mime_type="application/pdf",
                size=11,
            )])
            with patch("schema.parse_document", return_value=[parsed]), patch(
                "schema.extract_tax_fields"
            ) as extract:
                with self.assertRaisesRegex(ValueError, "Recognized Utah TC-20 return"):
                    solve(request)
                extract.assert_not_called()


if __name__ == "__main__":
    unittest.main()
