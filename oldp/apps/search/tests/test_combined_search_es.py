r"""Real-Elasticsearch integration tests for combined citation + keyword + facets search.

Verifies the post-fix behaviour end-to-end: the web /search/ view, the REST
/api/cases/search/ endpoint, and the MCP search_cases tool all intersect
citation filters with keyword and facet filters instead of letting one of
them silently win.

Skipped under the default mock backend (MOCK_ES_TESTS=True). Runs in the CI
``test-es`` job and locally via:

    DJANGO_MOCK_ES_TESTS="False" DJANGO_CONFIGURATION=TestConfiguration \
        .venv/bin/python manage.py test \
        oldp.apps.search.tests.test_combined_search_es --tag es
"""

from django.test import TestCase, override_settings
from django.urls import reverse

from oldp.apps.cases.mcp import CaseTools
from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.references.models import CaseReferenceMarker, Reference
from oldp.utils.test_utils import ElasticsearchTestMixin, real_es_test


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "combined-search-es-tests",
        }
    },
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
    },
)
class CombinedSearchRealESTest(ElasticsearchTestMixin, TestCase):
    """Index three cases with distinct (keyword, court, citation) signatures
    and verify every combination of filters lands the right subset against
    a real ES cluster.
    """

    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.bgh = (
            Court.objects.filter(code__iexact="BGH").first() or Court.objects.first()
        )
        cls.lg = (
            Court.objects.exclude(pk=cls.bgh.pk).first()
            if cls.bgh is not None
            else Court.objects.first()
        )

        cls.bgb_book = LawBook.objects.create(
            slug="bgb-combo",
            code="BGB-COMBO",
            title="BGB combined-search fixture",
            revision_date="2020-01-01",
            latest=True,
            review_status="accepted",
        )
        cls.law_823 = Law.objects.create(
            book=cls.bgb_book,
            slug="823",
            section="§ 823",
            title="Schadensersatzpflicht",
            content="Schadensersatzpflicht...",
            order=1,
            review_status="accepted",
        )
        cls.law_444 = Law.objects.create(
            book=cls.bgb_book,
            slug="444",
            section="§ 444",
            title="Haftungsausschluss",
            content="Haftungsausschluss...",
            order=2,
            review_status="accepted",
        )

        # Case A: keyword + BGH + cites §823 → matches all combined filters
        cls.case_a = Case.objects.create(
            court=cls.bgh,
            date="2020-06-15",
            file_number="A-1/20",
            slug="case-a-combo",
            title="Case A combo",
            type="Urteil",
            content="Mietrecht Streit über Schadensersatz nach Vermieterpflichten.",
            review_status="accepted",
        )
        # Case B: keyword + LG + cites §444 (different section)
        cls.case_b = Case.objects.create(
            court=cls.lg,
            date="2020-07-01",
            file_number="B-2/20",
            slug="case-b-combo",
            title="Case B combo",
            type="Urteil",
            content="Mietrecht und Wohnungsmiete vor der Kammer.",
            review_status="accepted",
        )
        # Case C: different keyword + BGH + cites §823
        cls.case_c = Case.objects.create(
            court=cls.bgh,
            date="2020-08-12",
            file_number="C-3/20",
            slug="case-c-combo",
            title="Case C combo",
            type="Urteil",
            content="Kaufrecht und Gewährleistung beim Verkäufer.",
            review_status="accepted",
        )

        cls._link(cls.case_a, cls.law_823)
        cls._link(cls.case_b, cls.law_444)
        cls._link(cls.case_c, cls.law_823)

    @classmethod
    def _link(cls, case, law):
        marker = CaseReferenceMarker.objects.create(
            referenced_by=case,
            text=law.section,
            start=0,
            end=10,
            line_number=1,
        )
        ref = Reference.objects.create(
            law=law,
            law_book_slug=law.book.slug,
            law_section_slug=law.slug,
            to=f"{law.book.slug}/{law.slug}",
        )
        marker.references.add(ref)

    def setUp(self):
        super().setUp()
        # Re-index Cases so the new ``cited_laws`` tokens hit ES. We also
        # need Law docs available for the resolver's label lookup, though
        # the citation field itself only lives on Case.
        self.index_fixtures(models=[Case, Law])

    def _search_pks(self, params):
        qd = "&".join(f"{k}={v}" for k, v in params.items())
        res = self.client.get(reverse("haystack_search") + "?" + qd)
        self.assertEqual(res.status_code, 200, msg=res.content[:500])
        return {int(r.pk) for r in res.context["object_list"]}

    def _rest_pks(self, params):
        qd = "&".join(f"{k}={v}" for k, v in params.items())
        res = self.client.get("/api/cases/search/?" + qd)
        self.assertEqual(res.status_code, 200, msg=res.content[:500])
        return {int(r["id"]) for r in res.json()["results"]}

    @real_es_test
    def test_web_q_intersects_citation(self):
        """``q=mietrecht + cited_law_book=bgb-combo + cited_law_section=823``
        must return only Case A (Case B fails citation, Case C fails kw).
        """
        pks = self._search_pks(
            {
                "q": "mietrecht",
                "cited_law_book": self.bgb_book.slug,
                "cited_law_section": "823",
            }
        )
        self.assertEqual(pks, {self.case_a.pk})

    @real_es_test
    def test_web_facets_intersect_citation_without_q(self):
        pks = self._search_pks(
            {
                "selected_facets": f"court_exact:{self.bgh.code}",
                "cited_law_book": self.bgb_book.slug,
                "cited_law_section": "823",
            }
        )
        self.assertEqual(pks, {self.case_a.pk, self.case_c.pk})

    @real_es_test
    def test_web_all_filters_combine(self):
        pks = self._search_pks(
            {
                "q": "mietrecht",
                "selected_facets": f"court_exact:{self.bgh.code}",
                "start_date": "2020-01-01",
                "end_date": "2020-12-31",
                "cited_law_book": self.bgb_book.slug,
                "cited_law_section": "823",
            }
        )
        self.assertEqual(pks, {self.case_a.pk})

    @real_es_test
    def test_web_citation_only_regression(self):
        """Pre-existing happy path must stay green: citation-only returns
        every case that cites the section.
        """
        pks = self._search_pks(
            {
                "cited_law_book": self.bgb_book.slug,
                "cited_law_section": "823",
            }
        )
        self.assertEqual(pks, {self.case_a.pk, self.case_c.pk})

    @real_es_test
    def test_web_facets_only_regression(self):
        """Locks in the Bug A fix in real ES: facets-only must not drop
        the narrow query into a fresh empty SQS.
        """
        pks = self._search_pks({"selected_facets": f"court_exact:{self.bgh.code}"})
        # Two of our three fixture cases are on BGH; we don't assert
        # equality because other fixture cases (loaded via cases/cases.json
        # is intentionally NOT in our fixtures list) won't be in the
        # index. Just verify the BGH ones are present.
        self.assertIn(self.case_a.pk, pks)
        self.assertIn(self.case_c.pk, pks)
        self.assertNotIn(self.case_b.pk, pks)

    @real_es_test
    def test_rest_intersects_text_and_citation(self):
        pks = self._rest_pks(
            {
                "text": "mietrecht",
                "cited_law_book": self.bgb_book.slug,
                "cited_law_section": "823",
            }
        )
        self.assertEqual(pks, {self.case_a.pk})

    @real_es_test
    def test_mcp_search_cases_intersects_query_and_citation(self):
        tools = CaseTools()
        result = tools.search_cases(
            query="mietrecht",
            cited_law_book=self.bgb_book.slug,
            cited_law_section="823",
            limit=10,
        )
        self.assertIn("results", result, msg=result)
        ids = {r["id"] for r in result["results"]}
        self.assertEqual(ids, {self.case_a.pk})
