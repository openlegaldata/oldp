import coreapi
import coreschema
import logging
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import cache_page
from django_filters.rest_framework import DjangoFilterBackend
from drf_haystack.filters import HaystackFilter
from drf_haystack.viewsets import HaystackViewSet
from rest_framework import status, viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from oldp.api import SmallResultsSetPagination
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
from oldp.apps.search.filters import SearchSchemaFilter

logger = logging.getLogger(__name__)


class CaseViewSet(viewsets.ModelViewSet):
    """
    ViewSet for cases.

    Supports listing, retrieving, creating, updating, and deleting cases.

    **Creating cases:**

    POST /api/cases/ with JSON body containing:
    - court_name (required): Court name for automatic resolution
    - file_number (required): Court file number
    - date (required): Publication date (YYYY-MM-DD)
    - content (required): Full case content in HTML
    - type (optional): Decision type (e.g., 'Urteil', 'Beschluss')
    - ecli (optional): European Case Law Identifier
    - abstract (optional): Case summary in HTML
    - title (optional): Case title
    - private (optional): Whether case is private (default: false)
    - extract_refs (optional): Extract references from content (default: true)

    The court is automatically resolved from the court_name.
    Returns 409 Conflict if a case with the same court and file_number exists.
    """

    permission_classes = [HasTokenPermission]
    token_resource = "cases"

    pagination_class = SmallResultsSetPagination  # limit page (content field blows up response size)
    queryset = Case.get_queryset()
    serializer_class = CaseSerializer
    # lookup_field = 'slug'

    filter_backends = (
        OrderingFilter,
        DjangoFilterBackend,
    )
    filterset_class = CaseAPIFilter
    ordering_fields = ("date",)

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "create":
            return CaseCreateSerializer
        return CaseSerializer

    @method_decorator(cache_page(60))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get_queryset(self):
        return Case.get_queryset().select_related("court").only(*CASE_API_FIELDS)

    def create(self, request, *args, **kwargs):
        """
        Create a new case.

        The court is automatically resolved from the provided court_name.
        References are extracted from content by default (configurable via extract_refs).
        The API token used for creation is tracked on the case.

        Returns:
            201 Created: {"id": <case_id>, "slug": "<case_slug>"}
            400 Bad Request: Validation errors or court not found
            409 Conflict: Case with same court and file_number already exists
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        # Get the API token from the request (set by authentication)
        api_token = getattr(request, "auth", None)

        # Create the case using the service
        creator = CaseCreator(extract_refs=data.get("extract_refs", True))

        case = creator.create_case(
            court_name=data["court_name"],
            file_number=data["file_number"],
            date=data["date"],
            content=data["content"],
            case_type=data.get("type"),
            ecli=data.get("ecli"),
            abstract=data.get("abstract"),
            title=data.get("title"),
            private=data.get("private", False),
            api_token=api_token,
            extract_refs=data.get("extract_refs", True),
        )

        # Return minimal response with id and slug
        response_serializer = CaseCreateResponseSerializer(
            {"id": case.id, "slug": case.slug}
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

    def get_default_schema_fields(self):
        return [
            # Search query field is required
            coreapi.Field(
                name="text",
                location="query",
                required=True,
                schema=coreschema.String(
                    description="Search query on text content (Lucence syntax support)."
                ),
                description="",
                example=[
                    _("search_example_query1"),
                    _("search_example_query2"),
                    _("search_example_query3"),
                ],
            )
        ]


class CaseSearchViewSet(HaystackViewSet):
    """Search view (list only)"""

    permission_classes = (AllowAny,)
    pagination_class = SmallResultsSetPagination  # limit page (content field blows up response size)
    index_models = [Case]
    serializer_class = CaseSearchSerializer
    filter_backends = (
        HaystackFilter,
        CaseSearchSchemaFilter,
    )
