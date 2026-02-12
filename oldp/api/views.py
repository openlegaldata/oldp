from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from oldp.api.mixins import ReviewStatusFilterMixin
from oldp.apps.accounts.permissions import HasTokenPermission
from oldp.apps.courts.models import City, Country, Court, State
from oldp.apps.courts.serializers import (
    CitySerializer,
    CountrySerializer,
    CourtCreateSerializer,
    CourtSerializer,
    StateSerializer,
)
from oldp.apps.courts.services import CourtCreator


class CourtViewSet(ReviewStatusFilterMixin, viewsets.ModelViewSet):
    permission_classes = [HasTokenPermission]
    token_resource = "courts"

    queryset = Court.objects.all().order_by("name")
    serializer_class = CourtSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ("court_type", "slug", "code", "state_id", "city_id")

    def get_permissions(self):
        """Return permissions based on action - require auth for write operations."""
        action = getattr(self, "action", None)
        if action in ["create", "update", "partial_update", "destroy"]:
            return [IsAuthenticated(), HasTokenPermission()]
        return [HasTokenPermission()]

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if getattr(self, "action", None) == "create":
            return CourtCreateSerializer
        return CourtSerializer

    def get_queryset(self):
        return super().get_queryset().select_related("created_by_token")

    def create(self, request, *args, **kwargs):
        """Create a new court.

        The state is resolved from state_name and city from city_name.
        Courts created via API are set to review_status='pending'.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        # Get the API token from request
        api_token = getattr(request, "auth", None)

        # Create the court
        creator = CourtCreator()
        court = creator.create_court(
            name=data["name"],
            code=data["code"],
            state_name=data["state_name"],
            court_type=data.get("court_type"),
            city_name=data.get("city_name"),
            jurisdiction=data.get("jurisdiction"),
            level_of_appeal=data.get("level_of_appeal"),
            aliases=data.get("aliases"),
            description=data.get("description"),
            homepage=data.get("homepage"),
            street_address=data.get("street_address"),
            postal_code=data.get("postal_code"),
            address_locality=data.get("address_locality"),
            telephone=data.get("telephone"),
            fax_number=data.get("fax_number"),
            email=data.get("email"),
            api_token=api_token,
        )

        # Return minimal response
        response_data = {
            "id": court.id,
            "slug": court.slug,
            "review_status": court.review_status,
        }

        return Response(response_data, status=status.HTTP_201_CREATED)


class CityViewSet(viewsets.ModelViewSet):
    queryset = City.objects.all().order_by("name")
    serializer_class = CitySerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ("state_id",)
    http_method_names = ["get", "head", "options"]


class StateViewSet(viewsets.ModelViewSet):
    queryset = State.objects.all().order_by("name")
    serializer_class = StateSerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ("country_id",)
    http_method_names = ["get", "head", "options"]


class CountryViewSet(viewsets.ModelViewSet):
    queryset = Country.objects.all().order_by("name")
    serializer_class = CountrySerializer

    filter_backends = (DjangoFilterBackend,)
    filter_fields = ("code",)
    http_method_names = ["get", "head", "options"]
