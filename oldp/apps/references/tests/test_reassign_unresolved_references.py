"""Tests for the ``reassign_unresolved_references`` management command.

The command's job is to re-resolve ``Reference`` rows whose target
``LawBook`` did not exist at original extraction time. The DSGVO bundle
ingest is the concrete trigger: ~141 markers locally and a much larger
set on prod were sitting with ``law_id IS NULL`` because no DSGVO row
existed in ``laws_lawbook`` when the cases were originally processed.

The tests below seed the failure shape directly (markers + refs with
``law_id=None``), import the EU ``LawBook`` rows, run the command, and
assert that the refs flip to a populated FK + the stable
``(law_book_slug, law_section_slug)`` pair.
"""

from datetime import date

from django.core.management import call_command
from django.test import TestCase, tag

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Country, Court, State
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.references.models import (
    CaseReferenceMarker,
    Reference,
    ReferenceFromCase,
)


@tag("commands")
class ReassignUnresolvedReferencesTestCase(TestCase):
    """Cover the multi-citation marker pairing logic + single-cite happy path."""

    @classmethod
    def setUpTestData(cls):
        country, _ = Country.objects.get_or_create(
            code="DE", defaults={"name": "Germany"}
        )
        state, _ = State.objects.get_or_create(
            pk=1,
            defaults={"name": "Test", "country": country, "slug": "test"},
        )
        cls.court = Court.objects.create(
            name="Court T",
            slug="court-t",
            code="T",
            state=state,
            review_status="accepted",
        )
        cls.case = Case.objects.create(
            court=cls.court,
            file_number="X 1/26",
            slug="x-1-26",
            date=date(2026, 1, 1),
            ecli="ECLI:DE:T:1",
            review_status="accepted",
        )

        # DSGVO LawBook + a handful of articles the test cites.
        cls.dsgvo_book = LawBook.objects.create(
            code="DSGVO",
            title="Datenschutz-Grundverordnung",
            slug="dsgvo",
            latest=True,
            revision_date=date(2016, 4, 27),
            review_status="accepted",
        )
        # Section labels match what the EUR-Lex provider stamps —
        # ``"Art. N"`` slugifies to ``"art-N"``. The resolver's fallback
        # chain must accept this form for the backfill to succeed.
        cls.law_art_15 = Law.objects.create(
            book=cls.dsgvo_book,
            section="Art. 15",
            slug="art-15",
            review_status="accepted",
        )
        cls.law_art_77 = Law.objects.create(
            book=cls.dsgvo_book,
            section="Art. 77",
            slug="art-77",
            review_status="accepted",
        )
        cls.law_art_5 = Law.objects.create(
            book=cls.dsgvo_book,
            section="Art. 5",
            slug="art-5",
            review_status="accepted",
        )

    def _make_marker_with_refs(self, text, count):
        """Build a CaseReferenceMarker with ``count`` unresolved Reference rows.

        Mirrors the original-extraction shape: each Reference carries
        ``to=marker.text`` and no ``law``/``case`` target.
        """
        marker = CaseReferenceMarker.objects.create(
            referenced_by=self.case,
            text=text,
            start=0,
            end=len(text),
        )
        refs = []
        for _ in range(count):
            ref = Reference.objects.create(to=text)
            ReferenceFromCase.objects.create(marker=marker, reference=ref)
            refs.append(ref)
        return marker, refs

    def test_single_citation_marker_resolves(self):
        """``Art. 15 DSGVO`` → exactly one ref flips to point at the Law row."""
        _, refs = self._make_marker_with_refs("Art. 15 DSGVO", count=1)
        self.assertIsNone(refs[0].law_id)

        call_command("reassign_unresolved_references")

        refs[0].refresh_from_db()
        self.assertEqual(refs[0].law_id, self.law_art_15.id)
        self.assertEqual(refs[0].law_book_slug, "dsgvo")
        self.assertEqual(refs[0].law_section_slug, "art-15")

    def test_multi_citation_marker_pairs_by_order(self):
        """``Art. 5, 15, 77 DSGVO`` → 3 citations pair 1:1 with 3 refs (PK order)."""
        _, refs = self._make_marker_with_refs("Art. 5, 15, 77 DSGVO", count=3)

        call_command("reassign_unresolved_references")

        # Pairing is PK-order; refex emits 5, 15, 77 in that order.
        for ref in refs:
            ref.refresh_from_db()
        self.assertEqual(refs[0].law_id, self.law_art_5.id)
        self.assertEqual(refs[1].law_id, self.law_art_15.id)
        self.assertEqual(refs[2].law_id, self.law_art_77.id)

    def test_count_mismatch_is_skipped(self):
        """If today's parse produces a different citation count than the
        recorded refs, the marker is skipped entirely — mis-pairing would
        write wrong Law FKs.
        """
        # Marker text parses to 1 citation but we seeded 2 refs. The
        # command must not touch either.
        _, refs = self._make_marker_with_refs("Art. 15 DSGVO", count=2)

        call_command("reassign_unresolved_references")

        for ref in refs:
            ref.refresh_from_db()
            self.assertIsNone(
                ref.law_id,
                msg=(
                    "Count-mismatched markers must be skipped; a populated "
                    "law_id here means the command paired refs blindly."
                ),
            )

    def test_dry_run_does_not_write(self):
        _, refs = self._make_marker_with_refs("Art. 15 DSGVO", count=1)

        call_command("reassign_unresolved_references", "--dry-run")

        refs[0].refresh_from_db()
        self.assertIsNone(refs[0].law_id)

    def test_already_resolved_refs_are_left_alone(self):
        """A ref that already has ``law`` set is not re-assigned even if the
        marker text now parses differently.
        """
        _, refs = self._make_marker_with_refs("Art. 15 DSGVO", count=1)
        # Pre-populate the ref with a different (wrong) law to prove we
        # don't overwrite. In real prod data this would never happen, but
        # the invariant matters: the command only touches law_id IS NULL.
        refs[0].law = self.law_art_77
        refs[0].save()

        call_command("reassign_unresolved_references")

        refs[0].refresh_from_db()
        self.assertEqual(
            refs[0].law_id,
            self.law_art_77.id,
            msg="Command must not overwrite already-resolved law_id values.",
        )

    def test_resolves_year_suffix_book_via_default_filter(self):
        """``§ N EnWG`` cites resolve to ``EnWG 2005`` when ``EnWG`` is
        in the default book set.

        This is the same path that recovers the ~30% of unresolved law
        references whose ``LawBook.code`` carries a year suffix on prod
        (EnWG 2005, GKG 2004, AufenthG 2004, BNatSchG 2009 …). The
        command must:
          1. include markers whose text contains the bare cite form,
          2. let ``assign_law_ref``'s year-suffix fallback do the
             lookup,
          3. write the slug from the year-stamped book (``enwg-2005``,
             not ``enwg``) so reverse-cite filters return hits.
        """
        enwg = LawBook.objects.create(
            code="EnWG 2005",
            title="Gesetz über die Elektrizitäts- und Gasversorgung",
            slug="enwg-2005",
            latest=True,
            revision_date=date(2026, 3, 29),
            review_status="accepted",
        )
        law = Law.objects.create(
            book=enwg, section="§ 100", slug="100", review_status="accepted"
        )
        _, refs = self._make_marker_with_refs("§ 100 EnWG", count=1)

        call_command("reassign_unresolved_references")

        refs[0].refresh_from_db()
        self.assertEqual(refs[0].law_id, law.id)
        self.assertEqual(refs[0].law_book_slug, "enwg-2005")

    def test_filter_by_book_flag(self):
        """``--book BGB`` confines the scan to markers mentioning BGB and
        leaves DSGVO refs untouched.
        """
        bgb = LawBook.objects.create(
            code="BGB",
            title="BGB",
            slug="bgb",
            latest=True,
            revision_date=date(2024, 1, 1),
            review_status="accepted",
        )
        Law.objects.create(
            book=bgb, section="§ 823", slug="823", review_status="accepted"
        )
        _, dsgvo_refs = self._make_marker_with_refs("Art. 15 DSGVO", count=1)
        _, bgb_refs = self._make_marker_with_refs("§ 823 BGB", count=1)

        call_command("reassign_unresolved_references", "--book", "BGB")

        dsgvo_refs[0].refresh_from_db()
        bgb_refs[0].refresh_from_db()
        self.assertIsNone(
            dsgvo_refs[0].law_id,
            msg="--book BGB must not touch DSGVO markers.",
        )
        self.assertIsNotNone(
            bgb_refs[0].law_id,
            msg="--book BGB should resolve BGB markers.",
        )
