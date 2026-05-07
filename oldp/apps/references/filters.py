"""Filters for the flat ``/api/references/`` resource.

Designed so users can pose cross-cutting graph questions via query
params: e.g. "all references involving cases dated 2020-2023 that
target BGB" via
``?cited_by_case__date__gte=2020-01-01&cites_law__book__slug=bgb``.

Both id-based and slug-based filter fields are exposed so callers
don't have to round-trip through ``/api/cases/?slug=…`` to get the id.
"""

from __future__ import annotations

import django_filters

from oldp.apps.references.models import Reference


class ReferenceFilter(django_filters.FilterSet):
    """Filterset for ``Reference`` rows.

    Filter aliases (preferred user-facing names) point at the underlying
    relationships:

    - ``cited_by_case`` / ``cited_by_case__slug`` — the source case
      whose body emitted the cite.
    - ``cited_by_law`` / ``cited_by_law__slug`` /
      ``cited_by_law__book__slug`` — the source law whose body emitted
      the cite.
    - ``cites_case`` / ``cites_case__slug`` — the target case (the
      ``Reference.case`` FK).
    - ``cites_law`` / ``cites_law__slug`` /
      ``cites_law__book__slug`` — the target law (the ``Reference.law``
      FK).
    """

    # Source side (the case/law whose content emitted the cite). Reach
    # through the through-table → marker → referenced_by chain.
    cited_by_case = django_filters.NumberFilter(
        field_name="referencefromcase__marker__referenced_by_id"
    )
    cited_by_case__slug = django_filters.CharFilter(
        field_name="referencefromcase__marker__referenced_by__slug"
    )
    cited_by_law = django_filters.NumberFilter(
        field_name="referencefromlaw__marker__referenced_by_id"
    )
    cited_by_law__slug = django_filters.CharFilter(
        field_name="referencefromlaw__marker__referenced_by__slug"
    )
    cited_by_law__book__slug = django_filters.CharFilter(
        field_name="referencefromlaw__marker__referenced_by__book__slug"
    )

    # Target side (the case/law the cite resolves to). Reach via the
    # FKs on Reference.
    cites_case = django_filters.NumberFilter(field_name="case_id")
    cites_case__slug = django_filters.CharFilter(field_name="case__slug")
    cites_law = django_filters.NumberFilter(field_name="law_id")
    cites_law__slug = django_filters.CharFilter(field_name="law__slug")
    cites_law__book__slug = django_filters.CharFilter(field_name="law__book__slug")

    # Convenience: only assigned references (drop unresolved ones).
    assigned = django_filters.BooleanFilter(method="filter_assigned")

    class Meta:
        model = Reference
        fields: list[str] = []

    def filter_assigned(self, queryset, name, value):
        if value:
            return queryset.exclude(case__isnull=True, law__isnull=True)
        return queryset.filter(case__isnull=True, law__isnull=True)
