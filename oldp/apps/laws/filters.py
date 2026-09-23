import django_filters
from django_filters.rest_framework import FilterSet as RESTFilterSet

from oldp.apps.laws.models import Law


class LawAPIFilter(RESTFilterSet):
    """Filters for ``/api/laws/`` and its ``citing_*`` actions.

    Declared explicitly for one reason: ``book_id`` is a ForeignKey, and
    django-filter's auto-generated filter for a FK is a ``ModelChoiceFilter``.
    The browsable API renders that as a ``<select>`` holding **one ``<option>``
    per law book** -- ~10,000 of them, which is 1.5 MB of HTML and ~1.7s on
    every ``?format=api`` request to any law endpoint, independent of how many
    results the request actually returns. A ``limit=1`` request paid it in
    full.

    ``NumberFilter`` accepts the same ``?book_id=<pk>`` query and issues the
    same SQL, but renders a plain number input. ``CaseAPIFilter.court`` already
    does this for the same reason.
    """

    book_id = django_filters.NumberFilter()

    class Meta:
        model = Law
        fields = ("book_id", "book__slug", "book__latest", "book__revision_date")
