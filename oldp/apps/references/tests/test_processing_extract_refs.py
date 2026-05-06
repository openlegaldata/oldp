from django.test import TestCase, TransactionTestCase, tag
from refex.citations import LawCitation, Span

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps.extract_refs import (
    ProcessingStep as ExtractRefsStep,
)
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.processing.errors import ProcessingError
from oldp.apps.references.models import Reference
from oldp.apps.references.processing.processing_steps.extract_refs import (
    BaseExtractRefs,
)


@tag("processing")
class ExtractReferencesTestCase(TransactionTestCase):
    """./manage.py dumpdata references --output refs.json"""

    fixtures = [
        "courts/default.json",
        "cases/case_with_references.json",
        "laws/empty_bgb.json",
    ]

    def test_extract_law_refs_from_case(self):
        case = Case.objects.get(pk=1888)

        # law_book_codes left unset — the extractor uses the bundled
        # legal-reference-extraction code list (~1947 codes + unit hints).
        step = ExtractRefsStep(
            law_refs=True,
            case_refs=False,
            assign_refs=True,
        )

        processed = step.process(case)

        # Counts updated for legal-reference-extraction 0.5.0, which adds
        # `Art.` / Grundgesetz citation patterns (CHANGELOG Stream E).
        # The fixture now yields 5 additional Art. GG markers for 3 new
        # target groups (GG/2, GG/14, GG/34) compared to v0.4.x.
        self.assertEqual(33, len(processed.get_references()))

        groups = processed.get_grouped_references()

        self.assertEqual(16, len(groups))


@tag("processing")
class AssignLawRefTestCase(TestCase):
    """Direct unit tests for ``BaseExtractRefs.assign_law_ref``.

    The legacy assignment used a bare ``str.lower`` / ``replace(' ', '')``
    normalization that silently failed for non-ASCII codes
    (``ÄApprO 2002`` ≠ ``aappro-2002``) and for Grundgesetz Articles
    (refex emits ``number="1"`` for ``Art. 1 GG`` but the stored
    ``Law.slug`` is ``"artikel-1"``). It also missed the
    ``book__latest=True`` filter, so multiple revisions of one book
    matched the same ``(slug, slug)`` and ``.first()`` returned a
    non-deterministic stale revision.

    These tests pin the corrected behaviour: Django ``slugify``,
    unit-aware section slug, latest-revision filter, with a bare-slug
    fallback for Articles whose stored slug skips the ``"artikel-"``
    prefix.
    """

    def setUp(self):
        # Resolver borrows BaseExtractRefs directly; no engines needed.
        class _Resolver(BaseExtractRefs):
            pass

        self.resolver = _Resolver()

    def _make_book(self, *, code, slug, latest=True, revision_date):
        return LawBook.objects.create(
            code=code,
            title=code,
            slug=slug,
            latest=latest,
            revision_date=revision_date,
        )

    def _make_law(self, *, book, section, slug):
        return Law.objects.create(
            book=book,
            section=section,
            slug=slug,
            content="",
            title="",
        )

    def test_resolves_paragraph_citation(self):
        book = self._make_book(code="BGB", slug="bgb", revision_date="2024-01-01")
        law = self._make_law(book=book, section="§ 823", slug="823")

        citation = LawCitation(
            span=Span(0, 9, "§ 823 BGB"),
            book="BGB",
            number="823",
            unit="paragraph",
        )
        ref = self.resolver.assign_law_ref(citation, Reference(to="§ 823 BGB"))

        self.assertEqual(ref.law_id, law.id)

    def test_resolves_grundgesetz_article(self):
        """Article cite ``unit="article"`` must build slug ``artikel-N``."""
        book = self._make_book(code="GG", slug="gg", revision_date="2024-01-01")
        law = self._make_law(book=book, section="Artikel 1", slug="artikel-1")

        citation = LawCitation(
            span=Span(0, 8, "Art. 1 GG"),
            book="GG",
            number="1",
            unit="article",
        )
        ref = self.resolver.assign_law_ref(citation, Reference(to="Art. 1 GG"))

        self.assertEqual(ref.law_id, law.id)

    def test_resolves_non_ascii_book_code(self):
        """``ÄApprO 2002`` slugifies to ``aappro-2002``."""
        book = self._make_book(
            code="ÄApprO 2002", slug="aappro-2002", revision_date="2024-01-01"
        )
        law = self._make_law(book=book, section="§ 35", slug="35")

        citation = LawCitation(
            span=Span(0, 14, "§ 35 ÄApprO 2002"),
            book="ÄApprO 2002",
            number="35",
            unit="paragraph",
        )
        ref = self.resolver.assign_law_ref(citation, Reference(to="§ 35 ÄApprO 2002"))

        self.assertEqual(ref.law_id, law.id)

    def test_prefers_latest_revision(self):
        """Two revisions, both with a Law/823: only the latest must match."""
        old_book = self._make_book(
            code="BGB", slug="bgb", latest=False, revision_date="2010-01-01"
        )
        new_book = self._make_book(
            code="BGB", slug="bgb", latest=True, revision_date="2024-01-01"
        )
        self._make_law(book=old_book, section="§ 823", slug="823")
        new_law = self._make_law(book=new_book, section="§ 823", slug="823")

        citation = LawCitation(
            span=Span(0, 9, "§ 823 BGB"),
            book="BGB",
            number="823",
            unit="paragraph",
        )
        ref = self.resolver.assign_law_ref(citation, Reference(to="§ 823 BGB"))

        self.assertEqual(
            ref.law_id,
            new_law.id,
            "Resolver returned a non-latest revision; book__latest=True "
            "filter is missing or being dropped.",
        )

    def test_article_falls_back_to_bare_slug(self):
        """Refex labels a cite ``article`` but the row stores its slug bare."""
        book = self._make_book(code="GG", slug="gg", revision_date="2024-01-01")
        # Stored slug "1" rather than "artikel-1" — fixture inconsistency.
        law = self._make_law(book=book, section="Artikel 1", slug="1")

        citation = LawCitation(
            span=Span(0, 8, "Art. 1 GG"),
            book="GG",
            number="1",
            unit="article",
        )
        ref = self.resolver.assign_law_ref(citation, Reference(to="Art. 1 GG"))

        self.assertEqual(ref.law_id, law.id)

    def test_raises_when_no_match(self):
        # No Law rows at all — assignment must surface as ProcessingError so
        # save_citations can count it toward the per-doc error rate.
        citation = LawCitation(
            span=Span(0, 9, "§ 999 ZZZ"),
            book="ZZZ",
            number="999",
            unit="paragraph",
        )
        with self.assertRaises(ProcessingError):
            self.resolver.assign_law_ref(citation, Reference(to="§ 999 ZZZ"))
