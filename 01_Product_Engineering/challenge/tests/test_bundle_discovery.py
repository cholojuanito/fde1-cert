import json
import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch


from schemas.api.extraction import TaxFact
from schemas.common.enum import (
    DocumentElementType,
    ExtractionArtifactFormat,
    ExtractionArtifactStatus,
    ObservationStatus,
    Parser,
    ReviewStatus,
    TaxDocumentType,
)
from schemas.common.types import MoneyValue, TextValue
from schemas.domain.tax_document import (
    BundleLinksDraft,
    FactDraft,
    FormDiscoveryDraft,
    FormExtractionDraft,
    PrintedLocator,
    DiscoveredFormDraft,
)
from schemas.extraction.extraction import (
    DocumentElement,
    ExtractedPage,
    ExtractionArtifact,
    SourceDocument,
    SourceLocation,
)
from schema import _run_stage, process_bundle


def artifact(two_pages=False):
    pages = []
    for number, text in enumerate(
        ["Schedule K-1 2025 Box 19 code A 1430", "Supporting statement code D 2233"]
        if two_pages
        else ["Uncatalogued narrative statement 2025 amount 12"],
        1,
    ):
        pages.append(
            ExtractedPage(
                artifact_id="a",
                page_number=number,
                width=10,
                height=10,
                elements=[
                    DocumentElement(
                        id=f"e{number}",
                        artifact_id="a",
                        kind=DocumentElementType.TEXT,
                        text=text,
                        locations=[SourceLocation(page=number)],
                    )
                ],
            )
        )
    return ExtractionArtifact(
        id="a",
        source_document=SourceDocument(
            id="s",
            filename="x.pdf",
            sha256="s",
            page_count=len(pages),
            storage_uri="file:///x.pdf",
        ),
        parser=Parser.DOCLING,
        parser_version="test",
        config={},
        status=ExtractionArtifactStatus.COMPLETED,
        format=ExtractionArtifactFormat.JSON,
        created_at=datetime.now(timezone.utc),
        pages=pages,
    )


def discovery(pages):
    return FormDiscoveryDraft(
        forms=[
            DiscoveredFormDraft(
                id="model-form",
                document_type=TaxDocumentType.OTHER,
                form_id="Narrative",
                tax_year=2025,
                page_numbers=pages,
                evidence_element_ids=[f"e{pages[0]}"],
            )
        ]
    )


class GenericBundleWorkflowTests(unittest.TestCase):
    def test_uncatalogued_form_resolves_parser_provenance(self):
        draft = FormExtractionDraft(
            facts=[
                FactDraft(
                    id="temp",
                    field_id="narrative.amount",
                    observation_status=ObservationStatus.OBSERVED,
                    value=MoneyValue(amount=Decimal("12")),
                    locator=PrintedLocator(label="amount"),
                    evidence_element_ids=["e1"],
                    reason="Printed amount",
                )
            ]
        )
        with patch(
            "schema._run_stage", side_effect=[discovery([1]), draft, BundleLinksDraft()]
        ):
            result = process_bundle(artifact())
        fact = result.forms[0].facts[0]
        self.assertEqual(
            fact.sources[0].text, "Uncatalogued narrative statement 2025 amount 12"
        )
        self.assertEqual(fact.sources[0].locations[0].page, 1)
        self.assertEqual(fact.fact.status, ReviewStatus.EXTRACTED)

    def test_completed_stage_replays_from_its_checkpoint(self):
        raw = FormDiscoveryDraft().model_dump_json()

        def complete(_prompt, _model, response_sink):
            response_sink(raw)
            return FormDiscoveryDraft()

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"EXTRACTION_CHECKPOINT_DIR": directory}):
                with patch("schema.run_extraction_stage", side_effect=complete) as run:
                    _run_stage(
                        artifact(), "discover", {}, FormDiscoveryDraft, "discover", None
                    )
                with patch(
                    "schema.run_extraction_stage",
                    side_effect=AssertionError("cached stage called the model"),
                ):
                    _run_stage(
                        artifact(), "discover", {}, FormDiscoveryDraft, "discover", None
                    )
            checkpoint = json.loads(
                (Path(directory) / "s" / "discover.json").read_text()
            )
        run.assert_called_once()
        self.assertIn("messages", checkpoint["request"])
        self.assertIn("e1", checkpoint["request"]["messages"]["evidence"])
        self.assertEqual(checkpoint["raw_response"], raw)

    def test_multi_page_form_extracts_every_page_without_truncation(self):
        first = FormExtractionDraft(
            facts=[
                FactDraft(
                    id="fact",
                    field_id="first.amount",
                    observation_status=ObservationStatus.OBSERVED,
                    value=MoneyValue(amount=1430),
                    locator=PrintedLocator(label="first"),
                    evidence_element_ids=["e1"],
                    reason="first page",
                )
            ]
        )
        second = FormExtractionDraft(
            facts=[
                FactDraft(
                    id="fact",
                    field_id="second.amount",
                    observation_status=ObservationStatus.OBSERVED,
                    value=MoneyValue(amount=2233),
                    locator=PrintedLocator(label="second"),
                    evidence_element_ids=["e2"],
                    reason="second page",
                )
            ]
        )
        with patch(
            "schema._run_stage",
            side_effect=[discovery([1, 2]), first, second, BundleLinksDraft()],
        ) as run:
            result = process_bundle(artifact(two_pages=True))
        self.assertEqual(
            [call.args[-1] for call in run.call_args_list[1:3]], [[1], [2]]
        )
        self.assertEqual(len(result.forms[0].facts), 2)

    def test_unknown_page_is_preserved_for_review(self):
        with patch(
            "schema._run_stage",
            side_effect=[
                discovery([1]),
                FormExtractionDraft(),
                FormExtractionDraft(),
                BundleLinksDraft(),
            ],
        ):
            result = process_bundle(artifact(two_pages=True))
        self.assertEqual(result.forms[1].form.document_type, TaxDocumentType.UNKNOWN)
        self.assertTrue(any("not assigned" in issue.message for issue in result.issues))

    def test_codes_are_distinct_and_duplicate_observations_are_reviewable(self):
        good = FormExtractionDraft(
            facts=[
                FactDraft(
                    id="a",
                    field_id="box.19",
                    code="A",
                    observation_status=ObservationStatus.OBSERVED,
                    value=MoneyValue(amount=1430),
                    locator=PrintedLocator(box="19", label="code A"),
                    evidence_element_ids=["e1"],
                    reason="A",
                ),
                FactDraft(
                    id="d",
                    field_id="box.19",
                    code="D",
                    observation_status=ObservationStatus.OBSERVED,
                    value=MoneyValue(amount=2233),
                    locator=PrintedLocator(box="19", label="code D"),
                    evidence_element_ids=["e1"],
                    reason="D",
                ),
            ]
        )
        with patch(
            "schema._run_stage", side_effect=[discovery([1]), good, BundleLinksDraft()]
        ):
            result = process_bundle(artifact())
        self.assertEqual(len(result.forms[0].facts), 2)

        repeated = FormExtractionDraft(
            facts=[good.facts[0], good.facts[0].model_copy(update={"id": "other"})]
        )
        with patch(
            "schema._run_stage",
            side_effect=[discovery([1]), repeated, BundleLinksDraft()],
        ):
            result = process_bundle(artifact())
        self.assertEqual(len(result.forms[0].facts), 1)
        self.assertEqual(len(result.forms[0].facts[0].sources), 2)
        self.assertEqual(
            result.forms[0].facts[0].fact.status, ReviewStatus.NEEDS_REVIEW
        )

        conflicting = FormExtractionDraft(
            facts=[
                good.facts[0],
                good.facts[0].model_copy(
                    update={"id": "other", "value": MoneyValue(amount=999)}
                ),
            ]
        )
        with patch(
            "schema._run_stage",
            side_effect=[discovery([1]), conflicting, BundleLinksDraft()],
        ):
            result = process_bundle(artifact())
        self.assertEqual(len(result.forms[0].facts), 2)
        self.assertEqual(result.forms[0].facts[1].fact.qualifiers["occurrence"], "2")
        self.assertTrue(
            any(
                issue.finding_type.value == "conflicting_values"
                for issue in result.issues
            )
        )

    def test_foreign_evidence_is_visible_but_reviewable(self):
        draft = FormExtractionDraft(
            facts=[
                FactDraft(
                    id="x",
                    field_id="amount",
                    observation_status=ObservationStatus.OBSERVED,
                    value=MoneyValue(amount=1),
                    locator=PrintedLocator(label="amount"),
                    evidence_element_ids=["e2"],
                    reason="wrong page",
                )
            ]
        )
        with patch(
            "schema._run_stage",
            side_effect=[
                discovery([1]),
                draft,
                FormExtractionDraft(),
                BundleLinksDraft(),
            ],
        ):
            result = process_bundle(artifact(two_pages=True))
        fact = result.forms[0].facts[0]
        self.assertEqual(fact.fact.status, ReviewStatus.NEEDS_REVIEW)
        self.assertFalse(fact.sources)
        self.assertTrue(
            any(
                issue.finding_type.value == "missing_evidence"
                for issue in result.issues
            )
        )

    def test_textless_artifact_skips_model(self):
        empty = artifact()
        empty.pages[0].elements[0].text = None
        with patch("schema._run_stage") as run:
            result = process_bundle(empty)
        run.assert_not_called()
        self.assertFalse(result.forms)
        self.assertTrue(any("No readable" in issue.message for issue in result.issues))


if __name__ == "__main__":
    unittest.main()
