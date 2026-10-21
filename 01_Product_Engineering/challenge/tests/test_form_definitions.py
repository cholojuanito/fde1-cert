import unittest
from datetime import datetime, timezone

from schemas.common.enum import (
    DocumentElementType,
    ExtractionArtifactFormat,
    ExtractionArtifactStatus,
    ExtractionMethod,
    Parser,
    TaxReturnType,
)
from schemas.domain.forms.factory import (
    FormIdentity,
    UnsupportedFormDefinition,
    create_form_definition,
    identify_form,
)
from schemas.extraction.extraction import (
    DocumentElement,
    ExtractedPage,
    ExtractionArtifact,
    SourceDocument,
    SourceLocation,
)


def definition(return_type, year):
    return create_form_definition(FormIdentity(
        return_type=return_type,
        tax_year=year,
        schedule="K-1",
    ))


def field(form, field_id):
    return next(item for item in form.fields if item.id == field_id)


class FormDefinitionTests(unittest.TestCase):
    def test_same_tc65_semantic_field_maps_to_each_years_box(self):
        old = field(definition(TaxReturnType.UTAH_TC65, 2024), "recipient.percent_ownership")
        new = field(definition(TaxReturnType.UTAH_TC65, 2025), "recipient.percent_ownership")

        self.assertEqual(old.id, new.id)
        self.assertEqual(old.kind, new.kind)
        self.assertEqual(old.source.printed_locator, "F")
        self.assertEqual(new.source.printed_locator, "H")

    def test_tc20s_has_its_own_mapping_and_limited_field_is_tc65_only(self):
        tc20s_2024 = definition(TaxReturnType.UTAH_TC20S, 2024)
        tc20s_2025 = definition(TaxReturnType.UTAH_TC20S, 2025)
        self.assertEqual(field(tc20s_2024, "recipient.percent_ownership").source.printed_locator, "E")
        self.assertEqual(field(tc20s_2025, "recipient.percent_ownership").source.printed_locator, "G")
        self.assertEqual(field(tc20s_2025, "utah.tax_withheld").source.printed_locator, "20")
        self.assertEqual(len(tc20s_2025.fields), 8)
        self.assertNotIn("recipient.limited_partner", {item.id for item in tc20s_2025.fields})

    def test_tc20_is_recognized_but_not_treated_as_a_k1(self):
        identity = identify_form("Utah Corporation Franchise and Income Tax Return TC-20 2025")
        self.assertEqual(identity.return_type, TaxReturnType.UTAH_TC20)
        self.assertIsNone(identity.schedule)
        with self.assertRaisesRegex(UnsupportedFormDefinition, "requires a K-1 schedule"):
            create_form_definition(identity)

    def test_unsupported_year_has_a_clear_error(self):
        with self.assertRaisesRegex(UnsupportedFormDefinition, "No TC-65 K-1 definition"):
            definition(TaxReturnType.UTAH_TC65, 2026)

    def test_multiple_k1_pages_are_rejected(self):
        source = SourceDocument(
            id="source", filename="bundle.pdf", sha256="abc", page_count=2,
            storage_uri="file:///bundle.pdf",
        )
        pages = [
            ExtractedPage(
                artifact_id="artifact", page_number=page_number,
                width=612, height=792,
                elements=[DocumentElement(
                    id=f"element-{page_number}", artifact_id="artifact",
                    kind=DocumentElementType.HEADING,
                    text="Schedule K-1 - Partner's Share TC-65, Sch. K-1 2025",
                    locations=[SourceLocation(page=page_number)],
                    extraction_method=ExtractionMethod.NATIVE_TEXT,
                )],
            )
            for page_number in (1, 2)
        ]
        artifact = ExtractionArtifact(
            id="artifact", source_document=source, parser=Parser.DOCLING,
            parser_version="test", config={},
            status=ExtractionArtifactStatus.COMPLETED,
            format=ExtractionArtifactFormat.JSON,
            created_at=datetime.now(timezone.utc), pages=pages,
        )

        from schemas.domain.forms.factory import identify_artifact_form

        with self.assertRaisesRegex(ValueError, "one K-1 per PDF"):
            identify_artifact_form(artifact)

    def test_factory_returns_independent_definition_objects(self):
        first = definition(TaxReturnType.UTAH_TC65, 2025)
        second = definition(TaxReturnType.UTAH_TC65, 2025)
        first.fields[0].source.labels.append("mutated")
        self.assertNotIn("mutated", second.fields[0].source.labels)


if __name__ == "__main__":
    unittest.main()
