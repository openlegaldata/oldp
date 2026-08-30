import logging

import django_filters
from django.conf import settings
from django.core.cache import cache
from django.db import connection, models
from django.forms import HiddenInput, TextInput
from django.forms.widgets import NumberInput
from django.utils.translation import gettext_lazy as _
from django_filters import FilterSet
from django_filters.rest_framework import FilterSet as RESTFilterSet

from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court, State
from oldp.apps.laws.models import Law
from oldp.apps.lib.filters import LazyOrderingFilter
from oldp.apps.lib.widgets import (
    AutocompleteWidget,
    BootstrapDateRangeWidget,
    CheckboxLinkWidget,
    VisibleIfSetWidget,
)

logger = logging.getLogger(__name__)


# Bound what we're willing to hold in the cache. Past this the id list is
# large enough that pickling it costs more than re-running the query, and the
# API can't surface results that deep anyway (PAGINATE_UNTIL * max_limit).
_CITING_IDS_CACHE_MAX = 50_000


def _citing_case_ids_for_law(law_id) -> list[int]:
    """Ids of cases citing ``law_id``, cached for ``CACHE_TTL`` seconds.

    The underlying join walks ~55k rows to return ~9.7k ids for a popular
    section, and the prod slow log clocked it at avg 3.4s / **max 10.0s** --
    the upstream gateway timeout -- over 237 calls in a week
    (internal-tools#5). The docstring on the caller claims ~300ms; production
    disagrees.

    Caching is safe because this id set is purely *structural*: the query
    filters only on ``reference.law_id`` and applies no ``review_status``
    predicate, so the result does not vary by user. Visibility is applied
    afterwards by the caller's queryset, which is what keeps this cache
    shareable across anonymous, owner and staff requests alike.

    The set only changes when references are re-extracted (a batch job), so a
    ``CACHE_TTL`` staleness window is well within tolerance.
    """
    cache_key = f"citing_case_ids:law:{law_id}"
    try:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    except Exception:
        logger.warning("Citing-case id cache read failed", exc_info=True)

    hint = "STRAIGHT_JOIN" if connection.vendor == "mysql" else ""
    sql = f"""
        SELECT {hint} DISTINCT m.referenced_by_id
        FROM references_reference r
        JOIN references_casereferencemarker_references mr ON mr.reference_id = r.id
        JOIN references_casereferencemarker m ON m.id = mr.casereferencemarker_id
        WHERE r.law_id = %s
    """
    with connection.cursor() as cur:
        cur.execute(sql, (law_id,))
        case_ids = [row[0] for row in cur.fetchall() if row[0] is not None]

    if len(case_ids) <= _CITING_IDS_CACHE_MAX:
        try:
            cache.set(cache_key, case_ids, settings.CACHE_TTL)
        except Exception:
            logger.warning("Citing-case id cache write failed", exc_info=True)

    return case_ids


class BaseCaseFilter(FilterSet):
    """Generic filter for cases (used for front-end and API)"""

    court = django_filters.ModelChoiceFilter(
        field_name="court",
        label=_("Court"),
        queryset=Court.objects.all().only("id", "name"),
    )

    court__state = django_filters.ModelChoiceFilter(
        field_name="court__state",
        queryset=State.objects.all().only("id", "name"),
        label=_("State"),
    )

    has_reference_to_law = django_filters.NumberFilter(
        field_name="has_reference_to_law",
        method="filter_has_reference_to_law",
        label=_("Has reference to"),
        widget=VisibleIfSetWidget(
            queryset=Law.objects.select_related("book").defer(
                *Law.defer_fields_list_view
            ),
            attrs={"field_label": _("Has reference to")},
        ),
    )

    court__slug = django_filters.CharFilter()
    court__state__slug = django_filters.CharFilter()
    court__jurisdiction = django_filters.ChoiceFilter(
        label=_("Jurisdiction"),
        choices=[(name, name) for name in settings.COURT_JURISDICTIONS.keys()],
        widget=CheckboxLinkWidget(attrs={"class": "checkbox-links"}),
    )
    court__level_of_appeal = django_filters.ChoiceFilter(
        label=_("Level of Appeal"),
        choices=[(name, name) for name in settings.COURT_LEVELS_OF_APPEAL.keys()],
        widget=CheckboxLinkWidget(attrs={"class": "checkbox-links"}),
    )

    date = django_filters.DateFromToRangeFilter(
        label=_("Published on"),
        widget=BootstrapDateRangeWidget(attrs={"class": "date-picker form-control"}),
    )
    slug = django_filters.CharFilter()
    file_number = django_filters.CharFilter()
    ecli = django_filters.CharFilter()

    def filter_has_reference_to_law(self, queryset, name, value):
        """Restrict ``queryset`` to cases that cite the given ``law_id``.

        Implemented as two queries: resolve the citing case ids on the
        ``refs_ref_law_idx`` index (with STRAIGHT_JOIN to pin the JOIN
        order on MariaDB), then ``filter(id__in=...)``. The single-query
        form (``filter(casereferencemarker__...).distinct()``) ran
        20-25s on heavily cited sections such as ``§ 823 BGB`` because
        MariaDB couldn't push ``ORDER BY date DESC LIMIT N`` through the
        wide JOIN + DISTINCT; the split shape runs in ~300ms.

        The id resolution is cached: see :func:`_citing_case_ids_for_law`.
        """
        case_ids = _citing_case_ids_for_law(value)
        if not case_ids:
            return queryset.none()
        return queryset.filter(id__in=case_ids)


class CaseFilter(BaseCaseFilter):
    """Front-end filters"""

    o = LazyOrderingFilter(
        fields=(
            ("date", "date"),
            ("updated_date", "updated_date"),  # not used in template
            ("file_number", "file_number"),
        ),
        field_labels={
            "date": _("Publication date"),
            "updated_date": _("Last modified date"),
            "file_number": _("File number"),
        },
        initial="-date",  # is overwritten in SortableFilterView
        # widget=forms.HiddenInput,
    )

    class Meta:
        model = Case
        fields = []
        filter_overrides = {
            models.CharField: {
                "filter_class": django_filters.CharFilter,
                "extra": lambda f: {
                    "lookup_expr": "icontains",
                },
            },
        }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Set front-end widgets

        # Unset fields (remove these filters from URL-params)
        del self.filters["file_number"]
        del self.filters["ecli"]
        del self.filters["slug"]
        del self.filters["court__state__slug"]

        # Hidden widgets
        for field_name in ["court__slug"]:
            self.filters.get(field_name).field.widget = HiddenInput()

        # Extra widgets
        self.filters.get("court").field.widget = AutocompleteWidget(
            url="courts:autocomplete",
            placeholder=_("Court"),
            queryset=Court.objects.all().only("id", "name"),
        )

        self.filters.get("court__state").field.widget = AutocompleteWidget(
            url="courts:state_autocomplete",
            placeholder=_("State"),
            queryset=State.objects.all().only("id", "name"),
        )
        # self.filters.get('has_reference_to_law').field.widget = VisibleIfSetInput(model=Law, model_related='book')


class CaseAPIFilter(RESTFilterSet, BaseCaseFilter):
    court = (
        django_filters.NumberFilter()
    )  # Choice list would be too large for regular choice field
    review_status = django_filters.ChoiceFilter(
        choices=[
            ("pending", "Pending"),
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
        ],
    )
    created_by_token = django_filters.NumberFilter(field_name="created_by_token_id")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # No fancy widgets
        self.filters.get("court__jurisdiction").field.widget = TextInput()
        self.filters.get("court__level_of_appeal").field.widget = TextInput()
        self.filters.get("has_reference_to_law").field.widget = NumberInput()
