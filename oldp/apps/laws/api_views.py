import logging

from django.conf import settings
from django.db import DataError, OperationalError
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from django_filters.rest_framework import DjangoFilterBackend
from drf_yasg.utils import swagger_auto_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import ListModelMixin
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSetMixin

from oldp.api import SmallResultsSetPagination
from oldp.api.mixins import ReviewStatusFilterMixin
from oldp.apps.accounts.permissions import HasTokenPermission
from oldp.apps.cases.serializers import CaseListSerializer
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.search_indexes import LawIndex
from oldp.apps.laws.serializers import (
    LawBookCreateSerializer,
    LawBookSerializer,
    LawCreateSerializer,
    LawListSerializer,
    LawSearchSerializer,
    LawSerializer,
)
from oldp.apps.laws.services import LawBookCreator, LawCreator
from oldp.apps.references.serializers import (
    ForwardReferencesResponseSerializer,
)
from oldp.apps.references.services import (
    citing_laws_for_law,
    law_forward_references,
)
from oldp.apps.search.api import SearchFilter, SearchViewMixin
from oldp.apps.search.filters import SearchSchemaFilter

logger = logging.getLogger(__name__)


class LawViewSet(ReviewStatusFilterMixin, viewsets.ModelViewSet):
    """ViewSet for individual law sections.

    Lists, retrieves, creates, and updates law sections within law books.
    Filter by `book_id`, `book__slug`, `book__latest`, or `book__revision_date`.
    Write operations require authentication.

    Response shape mirrors the Case API:

    * **List** (`GET /api/laws/`) returns the summary serializer
      (`LawListSerializer`), which omits the potentially-large `content`
      field. Use this for pagination, indexing, and discovery.
    * **Detail** (`GET /api/laws/<id>/`) returns the full
      `LawSerializer`, including `content`. Use this when the HTML body
      of a specific section is actually needed.

    For whole-dataset access, prefer the data dumps over scripted
    pagination — see ``docs/data-dumps.md``.
    """

    permission_classes = [HasTokenPermission]
    token_resource = "laws"

    queryset = Law.objects.all().order_by("order")
    serializer_class = LawSerializer

    filter_backends = (DjangoFilterBackend,)
    filterset_fields = ("book_id", "book__slug", "book__latest", "book__revision_date")

    def get_permissions(self):
        """Return permissions based on action - require auth for write operations."""
        action = getattr(self, "action", None)
        if action in ["create", "update", "partial_update", "destroy"]:
            return [IsAuthenticated(), HasTokenPermission()]
        return [HasTokenPermission()]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        action = getattr(self, "action", None)
        if action == "create":
            return LawCreateSerializer
        if action == "list":
            # /api/laws/ excludes the large `content` field; use the
            # detail view (/api/laws/<id>/) to fetch a section's full
            # content. Mirrors the Case list/detail split.
            return LawListSerializer
        return LawSerializer

    def update(self, request, *args, **kwargs):
        """Update a law. Requires staff (moderation action). Mirrors CaseViewSet."""
        if not request.user.is_staff:
            raise PermissionDenied("Only staff users can update laws.")
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Partially update a law. Requires staff (moderation action)."""
        if not request.user.is_staff:
            raise PermissionDenied("Only staff users can update laws.")
        return super().partial_update(request, *args, **kwargs)

    @method_decorator(cache_page(settings.CACHE_TTL))
    @method_decorator(vary_on_headers("Authorization", "Accept-Language", "Host"))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset().select_related("book")
        # ``select_related("created_by_token")`` was unconditional — but
        # the only consumer of that JOIN is ``ReviewStatusFieldMixin``,
        # which only reads ``instance.created_by_token.user_id`` for
        # authenticated non-staff requests. For anonymous list traffic
        # (the dominant case) the LEFT OUTER JOIN to ``accounts_apitoken``
        # added a 25-PK-lookup tax on a rarely-touched table — cold
        # buffer pool turned a 100ms query into a 3s one. Only chain it
        # when the response actually needs it.
        request = getattr(self, "request", None)
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            qs = qs.select_related("created_by_token")
        # /api/laws/ uses LawListSerializer which omits ``content`` from
        # the response, but without ``.defer()`` the ORM still SELECTs
        # the heavy TEXT columns (``content``, ``footnotes``, plus
        # ``book__changelog`` / ``book__footnotes`` / ``book__sections``
        # via select_related).
        if getattr(self, "action", None) == "list":
            qs = qs.defer(*Law.defer_fields_list_view)
        return qs

    def create(self, request, *args, **kwargs):
        """Create a new law within a law book.

        The law book is resolved from book_code (uses latest revision by default).
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        # Get the API token from request
        api_token = getattr(request, "auth", None)

        # Create the law
        creator = LawCreator()
        try:
            law = creator.create_law(
                book_code=data["book_code"],
                section=data["section"],
                title=data["title"],
                content=data["content"],
                revision_date=data.get("revision_date"),
                slug=data.get("slug"),
                order=data.get("order", 0),
                amtabk=data.get("amtabk"),
                kurzue=data.get("kurzue"),
                doknr=data.get("doknr"),
                footnotes=data.get("footnotes"),
                api_token=api_token,
            )
        except (DataError, OperationalError) as exc:
            # MariaDB raises ``OperationalError (1366, "Incorrect string
            # value")`` when one of the text columns has a narrower
            # charset (latin1/utf8mb3) than the inbound payload requires.
            # Surfacing this as a 400 with a descriptive ``detail`` lets
            # clients log/triage the offending row instead of seeing an
            # opaque 500 with no JSON body. The underlying schema fix is
            # ``laws/migrations/0025_convert_utf8mb4``; this branch is a
            # belt-and-braces guard for any future column-level oversight
            # and for deployments that have not yet run migrations.
            logger.warning(
                "DB rejected law payload for book_code=%s section=%s: %s",
                data.get("book_code"),
                data.get("section"),
                exc,
            )
            raise serializers.ValidationError(
                {
                    "detail": (
                        "The database rejected the submitted content. This is "
                        "usually caused by characters that the column charset "
                        "cannot represent (e.g. 4-byte UTF-8 / extended Latin / "
                        "typographic quotes against a utf8mb3 or latin1 column)."
                    )
                }
            ) from exc

        # Return minimal response
        response_data = {
            "id": law.id,
            "slug": law.slug,
            "book_id": law.book_id,
            "review_status": law.review_status,
        }

        return Response(response_data, status=status.HTTP_201_CREATED)

    # --- Citation graph -------------------------------------------------
    #
    # Mirrors the case-side actions on ``CaseViewSet`` for symmetry. All
    # three actions share the service-layer queries that back the MCP
    # tools.

    @swagger_auto_schema(responses={200: ForwardReferencesResponseSerializer})
    @action(detail=True, methods=["get"], permission_classes=[AllowAny])
    def references(self, request, pk=None):
        """Forward references emitted by this law (laws + cases it cites).

        Most laws cite only other laws (intra-book ``§ N``
        cross-references); case citations from a law are rare but
        structurally supported.
        """
        law = self.get_object()
        return Response(law_forward_references(law))

    @swagger_auto_schema(responses={200: CaseListSerializer(many=True)})
    @action(
        detail=True,
        methods=["get"],
        permission_classes=[AllowAny],
        serializer_class=CaseListSerializer,
    )
    def citing_cases(self, request, pk=None):
        """Cases whose body cites this law section.

        Backed by Elasticsearch (``CaseIndex.cited_laws``). The
        ``(book_slug, section_slug)`` token is stable across book
        revisions, so cross-revision lookup is implicit — no
        sibling-id expansion needed.

        On ES failure raises ``SearchBackendTimeout`` (transient,
        retryable) or ``SearchBackendUnavailable`` (hard outage). Both
        serialise to 503 with a structured body; agents differentiate
        via the ``retryable`` field.
        """
        from oldp.apps.cases.search_indexes import cited_law_token
        from oldp.apps.search.exceptions import (
            SearchBackendTimeout,
            SearchBackendUnavailable,
        )
        from oldp.apps.search.utils import (
            citing_cases_queryset_via_es,
            is_search_backend_error,
            is_search_backend_timeout,
        )

        law = self.get_object()
        try:
            qs, _total = citing_cases_queryset_via_es(
                "cited_laws", cited_law_token(law.book.slug, law.slug)
            )
        except Exception as exc:
            if is_search_backend_timeout(exc):
                raise SearchBackendTimeout() from exc
            if is_search_backend_error(exc):
                raise SearchBackendUnavailable() from exc
            raise
        page = self.paginate_queryset(qs)
        serializer = CaseListSerializer(page if page is not None else qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @swagger_auto_schema(responses={200: LawListSerializer(many=True)})
    @action(
        detail=True,
        methods=["get"],
        permission_classes=[AllowAny],
        serializer_class=LawListSerializer,
    )
    def citing_laws(self, request, pk=None):
        """Laws whose body cites this law section.

        Returns paginated summary records (``LawListSerializer``) —
        ``content`` is omitted; fetch ``/api/laws/<id>/`` if the full
        body of a citing law is needed.

        Resolved from the ``(book_slug, section_slug)`` pair, which is
        stable across book revisions — so cross-revision lookup is
        implicit and no sibling-id expansion is needed (same rationale
        as :meth:`citing_cases`).
        """
        law = self.get_object()
        qs = citing_laws_for_law((law.book.slug, law.slug))
        page = self.paginate_queryset(qs)
        serializer = LawListSerializer(page if page is not None else qs, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class LawBookViewSet(ReviewStatusFilterMixin, viewsets.ModelViewSet):
    """ViewSet for law books (e.g. BGB, StGB, GG).

    Lists, retrieves, creates, and updates law books. Each book can have
    multiple revisions identified by `revision_date`; the most recent is
    marked `latest=True`. Filter by `slug`, `code`, `latest`, or `revision_date`.
    Write operations require authentication.
    """

    permission_classes = [HasTokenPermission]
    token_resource = "lawbooks"

    queryset = LawBook.objects.all().order_by("code")
    serializer_class = LawBookSerializer

    filter_backends = (DjangoFilterBackend,)
    filterset_fields = ("slug", "code", "latest", "revision_date")

    def get_permissions(self):
        """Return permissions based on action - require auth for write operations."""
        action = getattr(self, "action", None)
        if action in ["create", "update", "partial_update", "destroy"]:
            return [IsAuthenticated(), HasTokenPermission()]
        return [HasTokenPermission()]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if getattr(self, "action", None) == "create":
            return LawBookCreateSerializer
        return LawBookSerializer

    def update(self, request, *args, **kwargs):
        """Update a law book. Requires staff (moderation action). Mirrors CaseViewSet."""
        if not request.user.is_staff:
            raise PermissionDenied("Only staff users can update law books.")
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Partially update a law book. Requires staff (moderation action)."""
        if not request.user.is_staff:
            raise PermissionDenied("Only staff users can update law books.")
        return super().partial_update(request, *args, **kwargs)

    @method_decorator(cache_page(settings.CACHE_TTL))
    @method_decorator(vary_on_headers("Authorization", "Accept-Language", "Host"))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("created_by_token")
            .defer("changelog", "footnotes", "sections")
        )

    def perform_update(self, serializer):
        """Persist an update and re-establish the latest-revision invariant.

        A ``review_status`` change via the API (e.g. approving a pending
        revision) must flip the ``latest`` flag to the newest accepted
        revision of the code. See :meth:`LawBook.refresh_latest_for_code`.
        """
        instance = serializer.save()
        LawBook.refresh_latest_for_code(instance.code)

    def create(self, request, *args, **kwargs):
        """Create a new law book.

        The new revision is created pending review (when submitted via an API
        token); it becomes the published ``latest`` revision only once accepted
        (see :meth:`LawBook.refresh_latest_for_code`). A directly-accepted
        revision that is newer than the current latest is promoted immediately.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        # Get the API token from request
        api_token = getattr(request, "auth", None)

        # Create the law book
        creator = LawBookCreator()
        try:
            lawbook = creator.create_lawbook(
                code=data["code"],
                title=data["title"],
                revision_date=data["revision_date"],
                order=data.get("order", 0),
                changelog=data.get("changelog"),
                footnotes=data.get("footnotes"),
                sections=data.get("sections"),
                api_token=api_token,
            )
        except (DataError, OperationalError) as exc:
            # See LawViewSet.create for rationale: prefer a 400 with a
            # descriptive body over a bare 500 when MariaDB rejects the
            # row at INSERT time due to column-charset mismatch.
            logger.warning(
                "DB rejected law book payload for code=%s revision_date=%s: %s",
                data.get("code"),
                data.get("revision_date"),
                exc,
            )
            raise serializers.ValidationError(
                {
                    "detail": (
                        "The database rejected the submitted content. This is "
                        "usually caused by characters that the column charset "
                        "cannot represent (e.g. 4-byte UTF-8 / extended Latin / "
                        "typographic quotes against a utf8mb3 or latin1 column)."
                    )
                }
            ) from exc

        # Return minimal response
        response_data = {
            "id": lawbook.id,
            "slug": lawbook.slug,
            "latest": lawbook.latest,
            "review_status": lawbook.review_status,
        }

        return Response(response_data, status=status.HTTP_201_CREATED)


class LawSearchSchemaFilter(SearchSchemaFilter):
    search_index_class = LawIndex

    def get_default_schema_operation_parameters(self):
        return [
            {
                "name": "text",
                "required": True,
                "in": "query",
                "description": "Search query on text content (Lucene syntax support).",
                "schema": {"type": "string"},
            }
        ]


class LawSearchViewSet(SearchViewMixin, ListModelMixin, ViewSetMixin, GenericAPIView):
    """Full-text search for law sections via Elasticsearch.

    Requires the `text` query parameter. Returns highlighted snippets by default;
    use `return_text=1` to include the full text. Supports date range filtering
    with `start_date` and `end_date`, and facet filtering (e.g. `book_code`).
    """

    permission_classes = (AllowAny,)
    pagination_class = SmallResultsSetPagination  # limit page (other content field blows up response size)
    search_models = [Law]
    serializer_class = LawSearchSerializer
    filter_backends = (
        SearchFilter,
        LawSearchSchemaFilter,
    )

    @method_decorator(cache_page(settings.CACHE_TTL))
    @method_decorator(vary_on_headers("Authorization", "Accept-Language", "Host"))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
