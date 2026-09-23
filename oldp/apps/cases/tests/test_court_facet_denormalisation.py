"""``Case.court_jurisdiction`` / ``court_level_of_appeal`` mirror the court.

Filtering ``courts_court.jurisdiction`` while ordering by ``cases_case.date``
spans two tables, so MariaDB led with the court index and merged one sorted
stream per matching court through a temp table + filesort. The prod slow log
had that as the top user-facing query: 66 calls, max 5.88s, 279,467 rows
examined to return a single 50-row page.

Denormalising is only safe while the copies stay true, so that -- not the
index -- is what these tests pin: the copy is written on save, follows a
reassignment to a different court, and is pushed down when a court is edited.
"""

from datetime import date

from django.test import TestCase

from oldp.apps.cases.filters import CaseFilter
from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court


class CourtFacetDenormalisationTestCase(TestCase):
    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    @classmethod
    def setUpTestData(cls):
        cls.ordinary = Court.objects.exclude(pk=Court.DEFAULT_ID).first()
        cls.ordinary.jurisdiction = "Ordentliche Gerichtsbarkeit"
        cls.ordinary.level_of_appeal = "Amtsgericht"
        cls.ordinary.save()

        cls.admin_court = Court.objects.exclude(
            pk__in=[Court.DEFAULT_ID, cls.ordinary.pk]
        ).first()
        cls.admin_court.jurisdiction = "Verwaltungsgerichtsbarkeit"
        cls.admin_court.level_of_appeal = "Verwaltungsgericht"
        cls.admin_court.save()

    def _case(self, court, tag):
        return Case.objects.create(
            court=court,
            file_number=tag,
            slug=tag.lower(),
            date=date(2026, 1, 1),
            ecli=f"ECLI:DE:TEST:{tag}",
            review_status="accepted",
        )

    def test_facets_are_copied_on_create(self):
        case = self._case(self.ordinary, "FAC1")

        case.refresh_from_db()
        self.assertEqual(case.court_jurisdiction, "Ordentliche Gerichtsbarkeit")
        self.assertEqual(case.court_level_of_appeal, "Amtsgericht")

    def test_facets_follow_a_court_reassignment(self):
        case = self._case(self.ordinary, "FAC2")

        case.court = self.admin_court
        case.save()

        case.refresh_from_db()
        self.assertEqual(case.court_jurisdiction, "Verwaltungsgerichtsbarkeit")
        self.assertEqual(case.court_level_of_appeal, "Verwaltungsgericht")

    def test_editing_a_court_updates_its_cases(self):
        case = self._case(self.ordinary, "FAC3")
        other = self._case(self.admin_court, "FAC4")

        self.ordinary.jurisdiction = "Arbeitsgerichtsbarkeit"
        self.ordinary.save()

        case.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(case.court_jurisdiction, "Arbeitsgerichtsbarkeit")
        # Untouched court's cases must not be collaterally rewritten.
        self.assertEqual(other.court_jurisdiction, "Verwaltungsgerichtsbarkeit")

    def test_clearing_a_court_facet_clears_it_on_cases(self):
        """The NULL direction -- the one a mismatch query would have missed."""
        case = self._case(self.ordinary, "FAC5")

        self.ordinary.jurisdiction = None
        self.ordinary.save()

        case.refresh_from_db()
        self.assertIsNone(case.court_jurisdiction)

    def test_setting_a_facet_from_null_reaches_cases_with_null(self):
        self.ordinary.jurisdiction = None
        self.ordinary.save()
        case = self._case(self.ordinary, "FAC6")
        self.assertIsNone(case.court_jurisdiction)

        self.ordinary.jurisdiction = "Finanzgerichtsbarkeit"
        self.ordinary.save()

        case.refresh_from_db()
        self.assertEqual(case.court_jurisdiction, "Finanzgerichtsbarkeit")

    def test_unrelated_court_edit_does_not_touch_cases(self):
        case = self._case(self.ordinary, "FAC7")
        before = Case.objects.get(pk=case.pk).updated_date

        self.ordinary.name = "Renamed Court"
        self.ordinary.save()

        case.refresh_from_db()
        self.assertEqual(case.court_jurisdiction, "Ordentliche Gerichtsbarkeit")
        self.assertEqual(case.updated_date, before)


class CourtFacetFilterTestCase(TestCase):
    """The public query params resolve against the denormalised columns.

    Asserted on the filterset rather than through ``GET /case/?...``: the
    jurisdiction/level choices come from ``settings.COURT_JURISDICTIONS``,
    which is ``{}`` in base oldp (the German values ship in oldp-de) and is
    read at class-definition time, so a view-level test here would only ever
    exercise "no valid choices" regardless of this change.
    """

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    @classmethod
    def setUpTestData(cls):
        cls.court = Court.objects.exclude(pk=Court.DEFAULT_ID).first()
        cls.court.jurisdiction = "Sozialgerichtsbarkeit"
        cls.court.level_of_appeal = "Amtsgericht"
        cls.court.save()

        other = Court.objects.exclude(pk__in=[Court.DEFAULT_ID, cls.court.pk]).first()
        other.jurisdiction = "Finanzgerichtsbarkeit"
        other.level_of_appeal = "Finanzgericht"
        other.save()

        cls.soz = Case.objects.create(
            court=cls.court,
            file_number="SOZ1",
            slug="soz1",
            date=date(2026, 1, 1),
            ecli="ECLI:DE:TEST:SOZ1",
            review_status="accepted",
        )
        cls.fin = Case.objects.create(
            court=other,
            file_number="FIN1",
            slug="fin1",
            date=date(2026, 1, 2),
            ecli="ECLI:DE:TEST:FIN1",
            review_status="accepted",
        )

    def test_public_param_names_are_unchanged(self):
        """``court__jurisdiction`` is in indexed URLs; it must keep working."""
        self.assertIn("court__jurisdiction", CaseFilter.declared_filters)
        self.assertIn("court__level_of_appeal", CaseFilter.declared_filters)

    def test_params_resolve_to_the_denormalised_columns(self):
        self.assertEqual(
            CaseFilter.declared_filters["court__jurisdiction"].field_name,
            "court_jurisdiction",
        )
        self.assertEqual(
            CaseFilter.declared_filters["court__level_of_appeal"].field_name,
            "court_level_of_appeal",
        )

    def test_filtering_selects_the_right_cases(self):
        qs = Case.objects.filter(court_jurisdiction="Sozialgerichtsbarkeit")

        self.assertEqual([c.pk for c in qs], [self.soz.pk])

    def test_level_of_appeal_selects_the_right_cases(self):
        qs = Case.objects.filter(court_level_of_appeal="Finanzgericht")

        self.assertEqual([c.pk for c in qs], [self.fin.pk])

    def test_filter_does_not_join_the_court_table(self):
        """The whole point: one table, so the sort can use the index."""
        qs = Case.objects.filter(court_jurisdiction="Sozialgerichtsbarkeit").order_by(
            "date"
        )

        self.assertNotIn("courts_court", str(qs.query))

    def test_index_covers_the_reported_query_shape(self):
        """review_status + facet + date, the shape from the slow log."""
        index_fields = {
            idx.name: idx.fields
            for idx in Case._meta.indexes  # noqa: SLF001
        }
        self.assertEqual(
            index_fields.get("cases_status_jur_date_idx"),
            ["review_status", "court_jurisdiction", "date"],
        )
        self.assertEqual(
            index_fields.get("cases_status_loa_date_idx"),
            ["review_status", "court_level_of_appeal", "date"],
        )
