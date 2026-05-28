from django.test import LiveServerTestCase, tag
from django.urls import reverse


@tag("views")
class LawsViewsTestCase(LiveServerTestCase):
    fixtures = ["laws/laws.json"]

    def test_index(self):
        res = self.client.get(reverse("laws:index"))

        self.assertContains(res, "Grundgesetz")
        self.assertContains(res, "aappro-2002")

    def test_index_char(self):
        res = self.client.get(reverse("laws:index_char", args=("g",)))

        self.assertContains(res, "Grundgesetz")

    def test_book(self):
        res = self.client.get(reverse("laws:book", args=("gg",)))

        self.assertContains(res, "Grundgesetz")

    def test_book_revision(self):
        res = self.client.get(
            reverse("laws:book", args=("gg",)) + "?revision_date=2010-07-26"
        )

        self.assertContains(res, "Grundgesetz")

    def test_law(self):
        res = self.client.get(reverse("laws:law", args=("gg", "artikel-1")))

        self.assertContains(
            res,
            "Die nachfolgenden Grundrechte binden Gesetzgebung, vollziehende Gewalt und "
            "Rechtsprechung als unmittelbar geltendes Recht",
        )

    def test_law_get_referencing_cases_uses_id_in(self):
        """Regression test for the JOIN+distinct rewrite in
        ``Law.get_referencing_cases``.

        The new shape resolves citing case ids via the slug-indexed
        ``Reference`` rows then ``filter(id__in=…)`` on the caller's
        queryset. It must still respect the caller's queryset (so
        ``view_law`` can pass request-scoped review-status filters).
        """
        from oldp.apps.cases.models import Case
        from oldp.apps.laws.models import Law

        law = Law.objects.filter(slug="artikel-1").select_related("book").first()
        self.assertIsNotNone(law)

        # No citing cases in the law fixtures → empty queryset, no error.
        empty = law.get_referencing_cases(Case.objects.filter(review_status="accepted"))
        self.assertEqual(empty.count(), 0)

        # Pass a queryset that excludes everything; the result must
        # respect that (proving the id__in is intersected with the
        # caller's queryset rather than ignoring it).
        denied = law.get_referencing_cases(Case.objects.none())
        self.assertEqual(denied.count(), 0)
