from decimal import Decimal
import unittest

from pydantic import ValidationError

from schemas.api.extraction import (
    BundleExtraction,
    ExtractionIssue,
    FormResult,
    TaxFact,
)
from schemas.audit.audit import FindingSeverity, FindingType
from schemas.common.enum import ObservationStatus, ReviewStatus, TaxDocumentType
from schemas.common.types import MoneyValue
from schemas.domain.bundle import BundleForm
from schemas.domain.tax_document import (
    FactReference,
    FactRelationship,
    FactSource,
    PrintedLocator,
    ProcessedBundle,
    ProcessedFact,
    ProcessedForm,
)
from schemas.extraction.extraction import SourceLocation
from schema import response_from_bundle


def fact(field_id="amount", code=None):
    return TaxFact(
        field_id=field_id,
        code=code,
        observation_status=ObservationStatus.OBSERVED,
        value=MoneyValue(amount=Decimal("0.00")),
        status=ReviewStatus.EXTRACTED,
    )


def form(identifier="form-1", facts=None):
    return FormResult(
        id=identifier,
        document_type=TaxDocumentType.OTHER,
        page_numbers=[1],
        facts=facts or [],
    )


class ResponseContractTests(unittest.TestCase):
    def test_code_aware_semantic_uniqueness(self):
        result = form(facts=[fact("box.19", "A"), fact("box.19", "D")])
        self.assertEqual(len(result.facts), 2)
        with self.assertRaisesRegex(ValidationError, "codes, and qualifiers"):
            form(facts=[fact("box.19", "A"), fact("box.19", "A")])

    def test_public_projection_excludes_internal_source_graph(self):
        source = FactSource(
            element_id="e1",
            locations=[SourceLocation(page=1)],
            text="Box 5 326",
            locator=PrintedLocator(box="5", label="Interest income"),
        )
        primary = ProcessedFact(id="fact-1", fact=fact("box.5"), sources=[source])
        component = ProcessedFact(
            id="fact-2", fact=fact("statement.interest"), sources=[source]
        )
        processed = ProcessedBundle(
            forms=[
                ProcessedForm(
                    form=BundleForm(
                        id="form-1",
                        document_type=TaxDocumentType.OTHER,
                        page_numbers=[1],
                    ),
                    facts=[primary, component],
                )
            ],
            relationships=[
                FactRelationship(
                    source=FactReference(form_id="form-1", fact_id="fact-2"),
                    target=FactReference(form_id="form-1", fact_id="fact-1"),
                    relationship="component_of",
                    evidence=[source],
                    status=ReviewStatus.EXTRACTED,
                )
            ],
        )
        response = response_from_bundle(processed)
        payload = response.model_dump(mode="json")
        self.assertEqual(set(payload), {"forms", "issues"})
        self.assertEqual(
            set(payload["forms"][0]),
            {
                "id",
                "document_type",
                "form_id",
                "jurisdiction",
                "tax_year",
                "page_numbers",
                "facts",
            },
        )
        self.assertEqual(
            set(payload["forms"][0]["facts"][0]),
            {"field_id", "observation_status", "value", "qualifiers", "code", "status"},
        )
        self.assertEqual(payload["forms"][0]["facts"][0]["value"]["amount"], "0.00")
        self.assertEqual(processed.relationships[0].evidence[0].locations[0].page, 1)

    def test_processed_bundle_rejects_unknown_references_and_cycles(self):
        item = ProcessedForm(
            form=BundleForm(
                id="form-1", document_type=TaxDocumentType.OTHER, page_numbers=[1]
            ),
            facts=[ProcessedFact(id="fact-1", fact=fact())],
        )
        with self.assertRaisesRegex(ValidationError, "known fact"):
            ProcessedBundle(
                forms=[item],
                relationships=[
                    FactRelationship(
                        source=FactReference(form_id="form-1", fact_id="fact-1"),
                        target=FactReference(form_id="form-1", fact_id="missing"),
                        relationship="repeats",
                        evidence=[],
                        status=ReviewStatus.EXTRACTED,
                    )
                ],
            )


if __name__ == "__main__":
    unittest.main()
