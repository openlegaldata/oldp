from django.db.models import Prefetch
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

    # Denormalized reverse-citation count (how often this case is cited by
    # other accepted cases), mirrored from ``Case.citing_cases_count``
    # (recomputed by the ``update_citing_counts`` command). Indexed as an
    # integer so results can be sorted "most cited first" for
    # landmark-precedent research. See ``docs/searching.md``.
    citing_cases_count = indexes.IntegerField(model_attr="citing_cases_count")

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

    def prepare_exact_matches(self, obj):
        """Navigational handles that should rank this case first.

        The case body (the document ``text`` field) does not reliably
        contain the case's own file number, and ``title`` is not the
        ``query_string`` default field — so without populating this field a
        file-number lookup matches nothing on-point. That lookup is a real
        path: an *unresolved* case citation renders a link to
        ``/search/?q=<file_number>&from=ref`` (see
        ``Reference.get_absolute_url``), and users paste Aktenzeichen
        directly. The search backend boosts an exact ``match_phrase`` on this
        field, so listing the file number (raw + whitespace-free) and the
        ECLI here makes the cited case rank #1.
        """
        forms = []
        if obj.file_number:
            forms.append(obj.file_number)
            # Whitespace-free variant so "VIZR123/22"-style pastes also hit.
            collapsed = obj.file_number.replace(" ", "")
            if collapsed != obj.file_number:
                forms.append(collapsed)
        if obj.ecli:
            forms.append(obj.ecli)
        return forms

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

    def _iter_prefetched_refs(self, obj):
        """Yield every ``Reference`` attached to ``obj`` via its case
        reference markers, using the per-batch prefetch chain set up by
        ``index_queryset``. Falls back to a direct query when the
        prefetch is absent (single-object reindex paths).
        """
        markers = getattr(obj, "_prefetched_markers", None)
        if markers is None:
            from oldp.apps.references.models import Reference

            yield from Reference.objects.filter(
                casereferencemarker__referenced_by_id=obj.pk
            )
            return
        for marker in markers:
            yield from marker._prefetched_refs

    def prepare_cited_laws(self, obj):
        """Distinct ``(law_book_slug, law_section_slug)`` pairs across
        the case's references. Empty slugs are skipped — those rows are
        unassigned references that haystack should not return as filter
        hits. Reads from the per-batch prefetch chain so each batch of
        1000 cases costs 2 SQL queries instead of 2000.
        """
        pairs = {
            (r.law_book_slug, r.law_section_slug)
            for r in self._iter_prefetched_refs(obj)
            if r.law_book_slug and r.law_section_slug
        }
        return [cited_law_token(book, section) for book, section in pairs]

    def prepare_cited_cases(self, obj):
        """Distinct cited-case PKs, stored as strings — haystack's
        ``MultiValueField`` tokenises each entry, and ES indexes the
        string form for filter lookups. Callers query with
        ``filter(cited_cases=str(case.pk))``.
        """
        ids = {
            r.case_id for r in self._iter_prefetched_refs(obj) if r.case_id is not None
        }
        return [str(i) for i in ids]

    def index_queryset(self, using=None):
        """Reindex-time queryset. The prefetch chain pulls every case's
        reference markers + the references through each marker in two
        extra SQL queries per batch (one per join level), so the per-row
        ``prepare_cited_laws`` / ``prepare_cited_cases`` work is pure
        Python — no SQL per case. Without this, each 1000-case batch
        triggered ~2000 individual ``Reference`` lookups.
        """
        from oldp.apps.references.models import CaseReferenceMarker, Reference

        refs_qs = Reference.objects.only(
            "id", "law_book_slug", "law_section_slug", "case_id"
        )
        markers_qs = CaseReferenceMarker.objects.only(
            "id", "referenced_by_id"
        ).prefetch_related(
            Prefetch("references", queryset=refs_qs, to_attr="_prefetched_refs"),
        )
        return (
            Case.get_queryset()
            .select_related("court", "court__state")
            .prefetch_related(
                Prefetch(
                    "casereferencemarker_set",
                    queryset=markers_qs,
                    to_attr="_prefetched_markers",
                ),
            )
        )
