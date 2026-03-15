import logging

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie, vary_on_headers
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.mixins import ListModelMixin
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from oldp.api import SmallResultsSetPagination
from oldp.api.mixins import ReviewStatusFilterMixin
from oldp.apps.accounts.permissions import HasTokenPermission
from oldp.apps.cases.filters import CaseAPIFilter
from oldp.apps.cases.models import Case
from oldp.apps.cases.search_indexes import CaseIndex
from oldp.apps.cases.serializers import (
    CASE_API_FIELDS,
    CaseCreateResponseSerializer,
    CaseCreateSerializer,
    CaseSearchSerializer,
    CaseSerializer,
)
from oldp.apps.cases.services import CaseCreator
from oldp.apps.search.api import SearchFilter, SearchViewMixin
from oldp.apps.search.filters import SearchSchemaFilter

logger = logging.getLogger(__name__)


class CaseViewSet(ReviewStatusFilterMixin, viewsets.ModelViewSet):
    """ViewSet for cases.

    Supports listing, retrieving, creating, updating, and deleting cases.

    **Creating cases:**

    POST /api/cases/?extract_refs=true with JSON body containing:
    - court_name (required): Court name for automatic resolution
    - file_number (required): Court file number
    - date (required): Publication date (YYYY-MM-DD)
    - content (required): Full case content in HTML
    - type (optional): Decision type (e.g., 'Urteil', 'Beschluss')
    - ecli (optional): European Case Law Identifier
    - abstract (optional): Case summary in HTML
    - title (optional): Case title
    - source (optional): Object with name (required) and homepage (optional).
      Looked up by name; created if not found. Default source used when omitted.
    Query parameters:
    - extract_refs (optional): Extract references from content (default: true)

    The court is automatically resolved from the court_name.
    Returns 409 Conflict if a case with the same court and file_number exists.
    """

    permission_classes = [HasTokenPermission]
    token_resource = "cases"

    pagination_class = (
        SmallResultsSetPagination  # limit page (content field blows up response size)
    )
    queryset = Case.objects.all()
    serializer_class = CaseSerializer
    # lookup_field = 'slug'

    filter_backends = (
        OrderingFilter,
        DjangoFilterBackend,
    )
    filterset_class = CaseAPIFilter
    ordering_fields = ("date",)

    def get_permissions(self):
        """Return permissions based on action - require auth for write operations."""
        action = getattr(self, "action", None)
        if action in ["create", "update", "partial_update", "destroy"]:
            return [IsAuthenticated(), HasTokenPermission()]
        return [HasTokenPermission()]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if getattr(self, "action", None) == "create":
            return CaseCreateSerializer
        return CaseSerializer

    @method_decorator(cache_page(settings.CACHE_TTL))
    @method_decorator(vary_on_headers("Authorization", "Accept-Language", "Host"))
    @method_decorator(vary_on_cookie)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("court", "created_by_token")
            .only(*CASE_API_FIELDS, "created_by_token_id", "created_by_token__user_id")
        )

    def create(self, request, *args, **kwargs):
        """Create a new case.

        The court is automatically resolved from the provided court_name.
        References are extracted from content by default (configurable via extract_refs query param).
        The API token used for creation is tracked on the case.

        Query parameters:
            extract_refs: Whether to extract references (default: true)

        Returns:
            201 Created: {"id": <case_id>, "slug": "<case_slug>"}
            400 Bad Request: Validation errors or court not found
            409 Conflict: Case with same court and file_number already exists
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        # Get extract_refs from query parameter (default: true)
        extract_refs_param = request.query_params.get("extract_refs", "true")
        extract_refs = extract_refs_param.lower() not in ("false", "0", "no")

        # Get the API token from the request (set by authentication)
        api_token = getattr(request, "auth", None)

        # Create the case using the service
        creator = CaseCreator(extract_refs=extract_refs)

        # Extract optional source info
        source_data = data.get("source")
        source_name = source_data["name"] if source_data else None
        source_homepage = source_data.get("homepage", "") if source_data else None

        case = creator.create_case(
            court_name=data["court_name"],
            file_number=data["file_number"],
            date=data["date"],
            content=data["content"],
            case_type=data.get("type"),
            ecli=data.get("ecli"),
            abstract=data.get("abstract"),
            title=data.get("title"),
            api_token=api_token,
            extract_refs=extract_refs,
            source_name=source_name,
            source_homepage=source_homepage,
        )

        # Return minimal response with id, slug, and review_status
        response_serializer = CaseCreateResponseSerializer(
            {"id": case.id, "slug": case.slug, "review_status": case.review_status}
        )

        logger.info(
            "Case created via API: id=%s, slug=%s, token=%s",
            case.id,
            case.slug,
            api_token.name if api_token else "None",
        )

        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class CaseSearchSchemaFilter(SearchSchemaFilter):
    search_index_class = CaseIndex

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


class CaseSearchViewSet(SearchViewMixin, viewsets.GenericViewSet, ListModelMixin):
    """Search view (list only)"""

    permission_classes = (AllowAny,)
    pagination_class = (
        SmallResultsSetPagination  # limit page (content field blows up response size)
    )
    search_models = [Case]
    serializer_class = CaseSearchSerializer
    filter_backends = (
        SearchFilter,
        CaseSearchSchemaFilter,
    )

    @method_decorator(cache_page(settings.CACHE_TTL))
    @method_decorator(vary_on_headers("Authorization", "Accept-Language", "Host"))
    @method_decorator(vary_on_cookie)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
