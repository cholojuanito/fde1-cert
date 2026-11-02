import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from extraction.context import plan_work_units
from schemas.common.enum import (
    DocumentElementType,
    ExtractionArtifactFormat,
    ExtractionArtifactStatus,
    Parser,
)
from schemas.extraction.extraction import (
    DocumentElement,
    ExtractedPage,
    ExtractionArtifact,
    SourceDocument,
    SourceLocation,
)


def artifact(page_texts: list[str]) -> ExtractionArtifact:
    return ExtractionArtifact(
        id="artifact",
        source_document=SourceDocument(
            id="source",
            filename="source.pdf",
            sha256="hash",
            page_count=len(page_texts),
            storage_uri="file:///source.pdf",
        ),
        parser=Parser.DOCLING,
        parser_version="test",
        config={},
        status=ExtractionArtifactStatus.COMPLETED,
        format=ExtractionArtifactFormat.JSON,
        created_at=datetime.now(timezone.utc),
        pages=[
            ExtractedPage(
                artifact_id="artifact",
                page_number=number,
                width=100,
                height=100,
                elements=[
                    DocumentElement(
                        id=f"e{number}",
                        artifact_id="artifact",
                        kind=DocumentElementType.TEXT,
                        text=text,
                        locations=[SourceLocation(page=number)],
                    )
                ],
            )
            for number, text in enumerate(page_texts, 1)
        ],
    )


class ContextPlanningTests(unittest.TestCase):
    def test_every_page_has_one_owner_and_neighbors_are_context_only(self):
        units = plan_work_units(
            artifact(["a" * 20, "b" * 20, "c" * 20]),
            max_tokens=8,
            context_pages=1,
        )
        self.assertEqual(
            [page for unit in units for page in unit.owned_page_numbers], [1, 2, 3]
        )
        self.assertEqual(units[0].context_page_numbers, (2,))
        self.assertEqual(units[1].context_page_numbers, (1, 3))
        self.assertEqual(units[2].context_page_numbers, (2,))

    def test_oversized_page_is_retained_as_an_explicit_work_unit(self):
        units = plan_work_units(artifact(["a" * 100]), max_tokens=5)
        self.assertEqual(units[0].owned_page_numbers, (1,))
        self.assertGreater(units[0].estimated_tokens, 5)


class RateLimitingTests(unittest.TestCase):
    def test_all_model_calls_reserve_their_input_tokens(self):
        from llm import _completion_kwargs

        messages = [{"role": "user", "content": "abcdefgh"}]
        with patch("llm._RATE_LIMITER.wait") as wait:
            _completion_kwargs(messages)
        wait.assert_called_once_with(2)


if __name__ == "__main__":
    unittest.main()
