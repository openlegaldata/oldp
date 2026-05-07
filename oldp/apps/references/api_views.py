"""Flat REST surfaces for citation graph + validation.

Two ViewSets:

- ``ReferenceViewSet`` — list/retrieve over ``Reference`` rows with
  rich slug-based filters (see :mod:`oldp.apps.references.filters`).
  Suits cross-cutting analytical queries that don't fit into the
  nested ``/api/cases/<id>/citing_cases/``-style actions on the case
  and law ViewSets.

- ``CitationViewSet`` — exposes :func:`validate_citation` as a
  detail-less ``GET /api/citations/validate/`` endpoint.

Both sit on the same service layer as the MCP toolset
(:mod:`oldp.apps.references.services`); see that module for the
underlying queries.
"""

from __future__ import annotations

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from oldp.apps.references.filters import ReferenceFilter
from oldp.apps.references.models import Reference
from oldp.apps.references.serializers import ReferenceSerializer
from oldp.apps.references.services import validate_citation


class ReferenceViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only flat resource over the citation graph.

    Most consumers should prefer the nested actions on
    ``/api/cases/<id>/`` and ``/api/laws/<id>/`` (``references``,
    ``citing_cases``, ``citing_laws``) — they map 1:1 to the common
    "what does X cite?" / "who cites X?" questions.

    This endpoint exists for queries the nested actions can't express:

    - cross-cutting filters across multiple dimensions (e.g. all cites
      by BGB-section laws to cases dated 2020-2023);
    - slug-based access without a prior id round-trip
      (``?cited_by_law__book__slug=bgb&cited_by_law__slug=823``);
    - aggregate / analytical queries over the full reference table.
    """

    permission_classes = [AllowAny]
    queryset = (
        Reference.objects.select_related("case", "case__court", "law", "law__book")
        .prefetch_related(
            "referencefromcase_set__marker__referenced_by",
            "referencefromlaw_set__marker__referenced_by__book",
        )
        .order_by("-id")
    )
    serializer_class = ReferenceSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = ReferenceFilter


class CitationViewSet(viewsets.GenericViewSet):
    """Procedural endpoints around citation strings (no underlying model).

    Currently just hosts the ``validate`` action; new procedural
    operations (citation parsing, batch validation, etc.) can join here.
    """

    permission_classes = [AllowAny]
    # Required by GenericViewSet's URL routing even though we don't list.
    queryset = Reference.objects.none()
    # No serializer used; validate() returns its own dict shape.
    serializer_class = ReferenceSerializer

    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def validate(self, request):
        """Validate a free-form German citation string.

        Query params:
            citation: the citation text (e.g. ``"§ 823 BGB"``).
            type: ``"auto"`` (default), ``"file_number"``, ``"ecli"``,
                or ``"law_reference"``.

        Returns the same dict shape as the MCP ``validate_citation`` tool.
        """
        citation = request.query_params.get("citation", "")
        ctype = request.query_params.get("type", "auto")
        return Response(validate_citation(citation, ctype))
