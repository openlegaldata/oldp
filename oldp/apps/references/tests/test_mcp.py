"""Unit tests for reference/citation MCP tools."""

from datetime import date

from django.test import TestCase, override_settings

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.references.mcp import ReferenceTools, _parse_citation_type
from oldp.apps.references.models import (
    CaseReferenceMarker,
    Reference,
    ReferenceFromCase,
)


class CitationParsingTests(TestCase):
    """Tests for citation type detection."""

    def test_ecli_detection(self):
        self.assertEqual(
            _parse_citation_type("ECLI:DE:BGH:2023:150623UIZR100.21.0"),
            "ecli",
        )

    def test_ecli_case_insensitive(self):
        self.assertEqual(
            _parse_citation_type("ecli:de:bgh:2023:test"),
            "ecli",
        )

    def test_paragraph_detection(self):
        self.assertEqual(
            _parse_citation_type("§ 823 BGB"),
            "law_reference",
        )

    def test_article_detection(self):
        self.assertEqual(
            _parse_citation_type("Art. 1 GG"),
            "law_reference",
        )

    def test_file_number_default(self):
        self.assertEqual(
            _parse_citation_type("VI ZR 123/22"),
            "file_number",
        )


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
)
class ReferenceToolsTests(TestCase):
    """Tests for citation validation and cross-reference tools."""

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def setUp(self):
        self.tools = ReferenceTools()
        self.court = Court.objects.filter(review_status="accepted").first()

        # Create test law book and law
        self.book = LawBook.objects.create(
            code="TESTBGB",
            title="Test BGB",
            slug="testbgb",
            latest=True,
            review_status="accepted",
        )
        self.law = Law.objects.create(
            book=self.book,
            section="823",
            title="Schadensersatzpflicht",
            slug="823",
            content="<p>Wer vorsaetzlich oder fahrlaessig...</p>",
            review_status="accepted",
        )

        # Create test cases
        if self.court:
            self.case_a = Case.objects.create(
                court=self.court,
                file_number="VI ZR 100/21",
                date=date(2023, 6, 15),
                content="<p>Case A referencing law.</p>",
                ecli="ECLI:DE:BGH:2023:TEST123",
                slug="ref-test-case-a",
                review_status="accepted",
            )
            self.case_b = Case.objects.create(
                court=self.court,
                file_number="VI ZR 200/22",
                date=date(2024, 1, 10),
                content="<p>Case B referencing case A.</p>",
                slug="ref-test-case-b",
                review_status="accepted",
            )

            # Create reference: case_a references the law
            self.ref_to_law = Reference.objects.create(
                law=self.law,
                to=f"law/{self.law.id}",
            )
            self.ref_to_law.set_to_hash()
            self.ref_to_law.save()

            self.marker_a = CaseReferenceMarker.objects.create(
                referenced_by=self.case_a,
                text="§ 823 BGB",
                start=0,
                end=10,
            )
            ReferenceFromCase.objects.create(
                marker=self.marker_a,
                reference=self.ref_to_law,
            )

            # Create reference: case_b references case_a
            self.ref_to_case = Reference.objects.create(
                case=self.case_a,
                to=f"case/{self.case_a.id}",
            )
            self.ref_to_case.set_to_hash()
            self.ref_to_case.save()

            self.marker_b = CaseReferenceMarker.objects.create(
                referenced_by=self.case_b,
                text="BGH VI ZR 100/21",
                start=0,
                end=20,
            )
            ReferenceFromCase.objects.create(
                marker=self.marker_b,
                reference=self.ref_to_case,
            )

    # --- validate_citation tests ---

    def test_validate_citation_empty(self):
        result = self.tools.validate_citation(citation="")
        self.assertIn("error", result)

    def test_validate_file_number_found(self):
        result = self.tools.validate_citation(citation="VI ZR 100/21")
        self.assertTrue(result["found"])
        self.assertEqual(result["type"], "case")
        self.assertEqual(len(result["matches"]), 1)

    def test_validate_file_number_not_found(self):
        result = self.tools.validate_citation(citation="XXXX 999/99")
        self.assertFalse(result["found"])

    def test_validate_ecli_found(self):
        result = self.tools.validate_citation(citation="ECLI:DE:BGH:2023:TEST123")
        self.assertTrue(result["found"])
        self.assertEqual(result["type"], "case")

    def test_validate_ecli_not_found(self):
        result = self.tools.validate_citation(citation="ECLI:DE:BGH:9999:NONEXISTENT")
        self.assertFalse(result["found"])

    def test_validate_law_reference_found(self):
        result = self.tools.validate_citation(citation="§ 823 TESTBGB")
        self.assertTrue(result["found"])
        self.assertEqual(result["type"], "law")

    def test_validate_law_reference_book_not_found(self):
        result = self.tools.validate_citation(citation="§ 1 FAKEBOOK")
        self.assertFalse(result["found"])

    def test_validate_law_reference_section_not_found(self):
        result = self.tools.validate_citation(citation="§ 99999 TESTBGB")
        self.assertFalse(result["found"])

    def test_validate_explicit_type(self):
        result = self.tools.validate_citation(
            citation="VI ZR 100/21", citation_type="file_number"
        )
        self.assertTrue(result["found"])

    # --- get_case_references tests ---

    def test_get_case_references_found(self):
        if not self.court:
            self.skipTest("No court fixture")
        result = self.tools.get_case_references(case_id=self.case_a.id)
        self.assertEqual(result["case_id"], self.case_a.id)
        self.assertGreaterEqual(result["total_law_references"], 1)
        # Check law ref content
        law_ref = result["law_references"][0]
        self.assertEqual(law_ref["section"], "823")

    def test_get_case_references_not_found(self):
        result = self.tools.get_case_references(case_id=999999)
        self.assertIn("error", result)

    def test_get_case_references_has_note(self):
        if not self.court:
            self.skipTest("No court fixture")
        result = self.tools.get_case_references(case_id=self.case_a.id)
        self.assertIn("note", result)

    # --- get_citing_cases tests ---

    def test_get_citing_cases_found(self):
        if not self.court:
            self.skipTest("No court fixture")
        result = self.tools.get_citing_cases(case_id=self.case_a.id)
        self.assertEqual(result["cited_case_id"], self.case_a.id)
        self.assertGreaterEqual(result["total_citing_cases"], 1)
        citing_ids = [c["id"] for c in result["results"]]
        self.assertIn(self.case_b.id, citing_ids)

    def test_get_citing_cases_not_found(self):
        result = self.tools.get_citing_cases(case_id=999999)
        self.assertIn("error", result)

    def test_get_citing_cases_limit(self):
        if not self.court:
            self.skipTest("No court fixture")
        result = self.tools.get_citing_cases(case_id=self.case_a.id, limit=1)
        self.assertLessEqual(len(result["results"]), 1)

    # --- get_cases_for_law tests ---

    def test_get_cases_for_law_by_id(self):
        result = self.tools.get_cases_for_law(law_id=self.law.id)
        self.assertGreaterEqual(result["total_citing_cases"], 1)
        citing_ids = [c["id"] for c in result["results"]]
        if self.court:
            self.assertIn(self.case_a.id, citing_ids)

    def test_get_cases_for_law_by_book_section(self):
        result = self.tools.get_cases_for_law(book_code="TESTBGB", section="823")
        self.assertGreaterEqual(result["total_citing_cases"], 0)

    def test_get_cases_for_law_not_found(self):
        result = self.tools.get_cases_for_law(law_id=999999)
        self.assertIn("error", result)

    def test_get_cases_for_law_no_params(self):
        result = self.tools.get_cases_for_law()
        self.assertIn("error", result)

    def test_get_cases_for_law_bad_book(self):
        result = self.tools.get_cases_for_law(book_code="FAKEBOOK", section="1")
        self.assertIn("error", result)

    def test_get_cases_for_law_resolves_bare_section_to_paragraph(self):
        """Regression: docs/mcp-test-report.md issue #3.

        Users (and LLM agents) typically pass bare section numbers like
        "823", but the database stores the prefixed form "§ 823".
        get_cases_for_law must normalize input the same way get_law_section
        does, otherwise the tool returns "Law section not found" for the
        most common input shape.
        """
        if not self.court:
            self.skipTest("No court fixture")

        # Add a law whose section is stored with the "§ " prefix and a
        # citation pointing at it; the bare number must still resolve.
        prefixed_law = Law.objects.create(
            book=self.book,
            section="§ 444",
            title="Prefixed section",
            slug="444",
            content="<p>Prefixed test law.</p>",
            review_status="accepted",
        )
        ref = Reference.objects.create(law=prefixed_law, to=f"law/{prefixed_law.id}")
        ref.set_to_hash()
        ref.save()
        marker = CaseReferenceMarker.objects.create(
            referenced_by=self.case_a,
            text="§ 444 BGB",
            start=20,
            end=30,
        )
        ReferenceFromCase.objects.create(marker=marker, reference=ref)

        # Bare number; must hit the "§ {section}" variant.
        result = self.tools.get_cases_for_law(book_code="TESTBGB", section="444")
        self.assertNotIn("error", result, msg=result)
        self.assertEqual(result["section"], "§ 444")
        self.assertGreaterEqual(result["total_citing_cases"], 1)

    def test_get_cases_for_law_aggregates_across_book_revisions(self):
        """Regression: docs/mcp-test-report.md issue #3.

        Reference.law_id is pinned to the Law revision that existed when
        the citation was extracted, which may be on an older LawBook
        (book.latest=False). Querying by (book_code, section) must union
        cases citing ANY revision, otherwise an agent that asks "which
        cases cite § 823 BGB?" gets zero hits even when 5,000+ cases cite
        the historical row.
        """
        if not self.court:
            self.skipTest("No court fixture")

        # Older revision of the same book + section. self.law (set up in
        # setUp on self.book with latest=True) plays the role of the
        # latest revision; this older row is what self.case_a actually
        # cites in setUp.
        older_book = LawBook.objects.create(
            code="TESTBGB",
            title="Test BGB (older revision)",
            slug="testbgb-old",
            latest=False,
            review_status="accepted",
        )
        older_law = Law.objects.create(
            book=older_book,
            section="823",
            title="Schadensersatzpflicht (older)",
            slug="823",
            content="<p>Older revision text.</p>",
            review_status="accepted",
        )

        # Re-point the existing reference at the older revision row
        # (mirrors production: extraction resolved to whichever id was
        # current at the time, then a newer revision was added later).
        self.ref_to_law.law = older_law
        self.ref_to_law.save()

        result = self.tools.get_cases_for_law(book_code="TESTBGB", section="823")
        self.assertNotIn("error", result, msg=result)
        self.assertGreaterEqual(
            result["total_citing_cases"],
            1,
            msg=(
                "Expected to find the case citing the OLDER law revision "
                "even though we queried by (book_code, section). The fix "
                "is to aggregate matching Law rows across all revisions."
            ),
        )
        citing_ids = [c["id"] for c in result["results"]]
        self.assertIn(self.case_a.id, citing_ids)

        # The response should report the canonical (latest) Law row's id,
        # not the older one used for the citation lookup.
        self.assertEqual(result["law_id"], self.law.id)
        self.assertEqual(result["book_code"], "TESTBGB")
