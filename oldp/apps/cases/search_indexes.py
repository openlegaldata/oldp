from haystack import indexes

from oldp.apps.cases.models import Case

# Separator for ``cited_laws`` tokens. Two underscores cannot appear
# inside a Django slug (slugs only use ``-`` and alphanumerics), so
# ``f"{book_slug}__{section_slug}"`` is always unambiguously parseable
# back into its two components and safe to use inside an ES query_string
# literal (no special characters).
CITED_LAW_SEPARATOR = "__"


def cited_law_token(book_slug: str, section_slug: str) -> str:
    """Render a cited-law token used by ``CaseIndex.cited_laws`` and
    by the search view's ``cited_law_book`` / ``cited_law_section``
    query params.
    """
    return f"{book_slug}{CITED_LAW_SEPARATOR}{section_slug}"


class CaseIndex(indexes.SearchIndex, indexes.Indexable):
    FACET_MODEL_NAME = "Case"

    text = indexes.CharField(document=True, use_template=True)
    title = indexes.CharField()
    absolute_url = indexes.CharField()
    model_type = indexes.CharField()

    review_status = indexes.CharField(model_attr="review_status")

    slug = indexes.CharField(model_attr="slug")

    facet_model_name = indexes.CharField(faceted=True)

    decision_type = indexes.CharField(faceted=True, null=True)
    court = indexes.CharField(faceted=True)
    court_jurisdiction = indexes.CharField(faceted=True, null=True)
    court_level_of_appeal = indexes.CharField(faceted=True, null=True)

    date = indexes.DateField(faceted=True)

    exact_matches = indexes.CharField()  # boost on exact match with this field

    # ``cited_laws``: multi-value list of ``"{book_slug}__{section_slug}"``
    # tokens for every law section this case cites. Powers the
    # ``/search/?cited_law_book=&cited_law_section=`` filter and the
    # citing-cases panel on ``/law/<book>/<sec>/``. Backed by ES's
    # inverted index, so the cold-cache cost of "all cases citing
    # § 823 BGB" drops from the ~3s SQL JOIN path to ~50ms.
    cited_laws = indexes.MultiValueField()
    # ``cited_cases``: multi-value list of Case PKs (as strings, since
    # haystack MultiValueField stores tokens) for every case this case
    # cites. Powers ``/search/?cited_case=<id>`` and the citing-cases
    # panel on ``/case/<slug>/``.
    cited_cases = indexes.MultiValueField()

    def get_model(self):
        return Case

    def prepare_title(self, obj):
        return obj.get_title()

    def prepare_absolute_url(self, obj):
        return obj.get_absolute_url()

    def prepare_model_type(self, obj):
        return "Case"

    def prepare_facet_model_name(self, obj):
        return self.FACET_MODEL_NAME

    def prepare_decision_type(self, obj):
        return obj.type

    def prepare_court(self, obj):
        return obj.court.code  # TODO short name?

    def prepare_court_jurisdiction(self, obj):
        return obj.court.jurisdiction

    def prepare_court_level_of_appeal(self, obj):
        return obj.court.level_of_appeal

    def prepare_date(self, obj):
        return obj.date  # .strftime('%Y-%m%-%d')

    def prepare_cited_laws(self, obj):
        """Collect distinct ``(law_book_slug, law_section_slug)`` pairs
        from every reference attached to one of the case's reference
        markers. Empty slugs are skipped — those rows are unassigned
        references that haystack should not return as filter hits.

        Querying ``Reference`` directly (rather than walking
        ``casereferencemarker_set`` → ``references``) keeps the per-row
        prepare cost to a single index-driven SELECT during reindex.
        """
        from oldp.apps.references.models import Reference

        pairs = (
            Reference.objects.filter(
                casereferencemarker__referenced_by_id=obj.pk,
            )
            .exclude(law_book_slug="")
            .exclude(law_section_slug="")
            .values_list("law_book_slug", "law_section_slug")
            .distinct()
        )
        return [cited_law_token(book, section) for book, section in pairs]

    def prepare_cited_cases(self, obj):
        """Collect distinct cited-case PKs.

        Stored as strings — haystack's ``MultiValueField`` tokenises
        each entry, and ES indexes the string form for filter lookups.
        Callers query with ``filter(cited_cases=str(case.pk))``.
        """
        from oldp.apps.references.models import Reference

        ids = (
            Reference.objects.filter(
                casereferencemarker__referenced_by_id=obj.pk,
                case_id__isnull=False,
            )
            .values_list("case_id", flat=True)
            .distinct()
        )
        return [str(i) for i in ids]

    def index_queryset(self, using=None):
        return Case.get_queryset().select_related("court", "court__state")
