from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie, vary_on_headers
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import ListModelMixin
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSetMixin

from oldp.api import SmallResultsSetPagination
from oldp.api.mixins import ReviewStatusFilterMixin
from oldp.apps.accounts.permissions import HasTokenPermission
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.search_indexes import LawIndex
from oldp.apps.laws.serializers import (
    LawBookCreateSerializer,
    LawBookSerializer,
    LawCreateSerializer,
    LawSearchSerializer,
    LawSerializer,
)
from oldp.apps.laws.services import LawBookCreator, LawCreator
from oldp.apps.search.api import SearchFilter, SearchViewMixin
from oldp.apps.search.filters import SearchSchemaFilter


class LawViewSet(ReviewStatusFilterMixin, viewsets.ModelViewSet):
    permission_classes = [HasTokenPermission]
    token_resource = "laws"

    queryset = Law.objects.all().order_by("order")
    serializer_class = LawSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ("book_id", "book__latest", "book__revision_date")

    def get_permissions(self):
        """Return permissions based on action - require auth for write operations."""
        action = getattr(self, "action", None)
        if action in ["create", "update", "partial_update", "destroy"]:
            return [IsAuthenticated(), HasTokenPermission()]
        return [HasTokenPermission()]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if getattr(self, "action", None) == "create":
            return LawCreateSerializer
        return LawSerializer

    @method_decorator(cache_page(settings.CACHE_TTL))
    @method_decorator(vary_on_headers("Authorization", "Accept-Language", "Host"))
    @method_decorator(vary_on_cookie)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().select_related("book", "created_by_token")

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

        # Return minimal response
        response_data = {
            "id": law.id,
            "slug": law.slug,
            "book_id": law.book_id,
            "review_status": law.review_status,
        }

        return Response(response_data, status=status.HTTP_201_CREATED)


class LawBookViewSet(ReviewStatusFilterMixin, viewsets.ModelViewSet):
    permission_classes = [HasTokenPermission]
    token_resource = "lawbooks"

    queryset = LawBook.objects.all().order_by("code")
    serializer_class = LawBookSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ("slug", "code", "latest", "revision_date")

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

    @method_decorator(cache_page(settings.CACHE_TTL))
    @method_decorator(vary_on_headers("Authorization", "Accept-Language", "Host"))
    @method_decorator(vary_on_cookie)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().select_related("created_by_token").defer(
            "changelog", "footnotes", "sections"
        )

    def create(self, request, *args, **kwargs):
        """Create a new law book.

        If this revision is newer than existing revisions for the same code,
        it automatically becomes the 'latest' revision.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        # Get the API token from request
        api_token = getattr(request, "auth", None)

        # Create the law book
        creator = LawBookCreator()
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
    """Search view"""

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
    @method_decorator(vary_on_cookie)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
