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
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from oldp.apps.references.filters import ReferenceFilter
from oldp.apps.references.models import Reference
from oldp.apps.references.serializers import (
    CitationValidationResponseSerializer,
    ReferenceSerializer,
)
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


class CitationViewSet(viewsets.ViewSet):
    """Procedural endpoints around citation strings (no underlying model).

    Plain ``ViewSet`` (not ``GenericViewSet``) on purpose: there's no
    queryset to list, so we sidestep the auto-injected ``limit`` /
    ``offset`` pagination params drf-yasg would otherwise stamp onto
    every action's schema.

    Currently just hosts the ``validate`` action; new procedural
    operations (citation parsing, batch validation, etc.) can join here.
    """

    permission_classes = [AllowAny]

    @swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                "citation",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=True,
                description=(
                    "The citation text to validate "
                    '(e.g. "§ 823 BGB", "VI ZR 123/22", '
                    '"ECLI:DE:BGH:2023:...").'
                ),
            ),
            openapi.Parameter(
                "type",
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                enum=["auto", "file_number", "ecli", "law_reference"],
                required=False,
                default="auto",
                description=(
                    "Type hint. ``auto`` (default) sniffs the input "
                    "shape; force a specific parser with the others."
                ),
            ),
        ],
        responses={200: CitationValidationResponseSerializer},
    )
    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def validate(self, request):
        """Validate a free-form German citation string.

        Returns the same dict shape as the MCP ``validate_citation`` tool:
        ``{found, type, matches[]}`` on success, ``{found: false, message}``
        when nothing matches, or ``{error}`` for invalid input.
        """
        citation = request.query_params.get("citation", "")
        ctype = request.query_params.get("type", "auto")
        return Response(validate_citation(citation, ctype))
