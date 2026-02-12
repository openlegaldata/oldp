from rest_framework import serializers

from oldp.api.mixins import ReviewStatusFieldMixin
from oldp.apps.courts.models import City, Country, Court, State


class CourtMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Court
        fields = (
            "id",
            "name",
            "slug",
            "city",
            "state",
            "jurisdiction",
            "level_of_appeal",
        )


class CourtSerializer(ReviewStatusFieldMixin, serializers.ModelSerializer):
    class Meta:
        model = Court
        fields = (
            "id",
            "name",
            "court_type",
            "city",
            "state",
            "code",
            "slug",
            "description",
            "image",
            "homepage",
            "street_address",
            "postal_code",
            "address_locality",
            "telephone",
            "fax_number",
            "jurisdiction",
            "level_of_appeal",
            "created_date",
            "updated_date",
            "review_status",
        )


# ============================================================================
# Creation Serializers
# ============================================================================


class CourtCreateSerializer(serializers.Serializer):
    """Serializer for creating courts via API.

    Accepts state_name and city_name instead of FKs, with automatic resolution.
    """

    # Required fields
    name = serializers.CharField(max_length=200, help_text="Full name of the court")
    code = serializers.CharField(
        max_length=20, help_text="Unique court code (e.g., 'BVerfG')"
    )
    state_name = serializers.CharField(
        max_length=50, help_text="State name for resolution"
    )

    # Optional fields
    court_type = serializers.CharField(
        max_length=10,
        required=False,
        allow_blank=True,
        help_text="Court type (AG, LG, ...)",
    )
    city_name = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        help_text="City name for resolution",
    )
    jurisdiction = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        help_text="Jurisdiction of court",
    )
    level_of_appeal = serializers.CharField(
        max_length=100, required=False, allow_blank=True, help_text="Level of appeal"
    )
    aliases = serializers.CharField(
        required=False, allow_blank=True, help_text="List of aliases (one per line)"
    )
    description = serializers.CharField(
        required=False, allow_blank=True, help_text="Court description"
    )
    homepage = serializers.URLField(
        required=False, allow_blank=True, help_text="Official court homepage"
    )
    street_address = serializers.CharField(
        max_length=200, required=False, allow_blank=True, help_text="Street address"
    )
    postal_code = serializers.CharField(
        max_length=200, required=False, allow_blank=True, help_text="Postal code"
    )
    address_locality = serializers.CharField(
        max_length=200, required=False, allow_blank=True, help_text="Address locality"
    )
    telephone = serializers.CharField(
        max_length=200, required=False, allow_blank=True, help_text="Telephone number"
    )
    fax_number = serializers.CharField(
        max_length=200, required=False, allow_blank=True, help_text="Fax number"
    )
    email = serializers.EmailField(
        required=False, allow_blank=True, help_text="Email address"
    )

    def validate_name(self, value):
        """Validate court name."""
        if not value or not value.strip():
            raise serializers.ValidationError("Court name cannot be empty.")
        return value.strip()

    def validate_code(self, value):
        """Validate court code."""
        if not value or not value.strip():
            raise serializers.ValidationError("Court code cannot be empty.")
        return value.strip()

    def validate_state_name(self, value):
        """Validate state name."""
        if not value or not value.strip():
            raise serializers.ValidationError("State name cannot be empty.")
        return value.strip()


class CourtCreateResponseSerializer(serializers.Serializer):
    """Serializer for court creation response."""

    id = serializers.IntegerField(help_text="Court ID")
    slug = serializers.CharField(help_text="Court slug")
    review_status = serializers.CharField(help_text="Review status")


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ("id", "name", "code")


class StateSerializer(serializers.ModelSerializer):
    class Meta:
        model = State
        fields = ("id", "name", "country", "slug")


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ("id", "name", "state")
