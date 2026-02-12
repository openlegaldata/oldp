from django.conf import settings as django_settings
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from oldp.api.mixins import ReviewStatusFieldMixin
from oldp.apps.cases.models import Case
from oldp.apps.cases.search_indexes import CaseIndex
from oldp.apps.courts.serializers import CourtMinimalSerializer
from oldp.apps.search.api import SearchResultSerializer

CASE_API_FIELDS = (
    "id",
    "slug",
    "court",
    "file_number",
    "date",
    "created_date",
    "updated_date",
    "type",
    "ecli",
    "content",
    "review_status",
)


class CaseSerializer(ReviewStatusFieldMixin, serializers.ModelSerializer):
    court = CourtMinimalSerializer(many=False, read_only=True)
    slug = serializers.ReadOnlyField()

    class Meta:
        model = Case
        fields = CASE_API_FIELDS

        lookup_field = "slug"


class CaseSearchSerializer(SearchResultSerializer):
    """Serializer for case search results."""

    class Meta:
        fields = [
            "slug",
            "date",
            "text",
            "court",
            "court_jurisdiction",
            "court_level_of_appeal",
            "decision_type",
        ]
        index_classes = [CaseIndex]


class SourceInputSerializer(serializers.Serializer):
    """Nested serializer for source information in case creation.

    If a source with the given name exists, it is reused. Otherwise a new source
    is created with the provided name and homepage.
    """

    name = serializers.CharField(help_text="Source name for lookup or creation")
    homepage = serializers.URLField(
        required=False,
        default="",
        allow_blank=True,
        help_text="Source homepage URL (used only when creating a new source)",
    )


class CaseCreateSerializer(serializers.Serializer):
    """Serializer for creating cases via API.

    Accepts court_name instead of court FK, with automatic resolution.
    Validates inputs based on CASE_CREATION_VALIDATION settings.
    """

    # Required fields
    court_name = serializers.CharField(
        help_text="Court name for automatic resolution (e.g., 'Bundesgerichtshof', 'AG Berlin')"
    )
    file_number = serializers.CharField(
        help_text="Court file number (e.g., 'I ZR 123/21')"
    )
    date = serializers.DateField(help_text="Publication date (YYYY-MM-DD format)")
    content = serializers.CharField(help_text="Full case content in HTML format")

    # Optional fields
    type = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Type of decision (e.g., 'Urteil', 'Beschluss')",
    )
    ecli = serializers.CharField(
        required=False, allow_blank=True, help_text="European Case Law Identifier"
    )
    abstract = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Case summary/abstract in HTML format",
    )
    title = serializers.CharField(
        required=False, allow_blank=True, help_text="Case title"
    )
    source = SourceInputSerializer(
        required=False,
        help_text="Source information (name, homepage). If omitted, the default source is used.",
    )

    def _get_validation_settings(self):
        """Get validation settings with defaults."""
        defaults = {
            "content_min_length": 10,
            "content_max_length": 10000000,
            "file_number_min_length": 1,
            "file_number_max_length": 100,
            "title_max_length": 255,
            "abstract_max_length": 50000,
            "court_name_max_length": 255,
        }
        settings = getattr(django_settings, "CASE_CREATION_VALIDATION", {})
        return {**defaults, **settings}

    def validate_court_name(self, value):
        """Validate court_name field."""
        settings = self._get_validation_settings()
        max_length = settings.get("court_name_max_length", 255)

        if not value or not value.strip():
            raise serializers.ValidationError(_("Court name cannot be empty."))

        if len(value) > max_length:
            raise serializers.ValidationError(
                _("Court name must not exceed %(max_length)s characters.")
                % {"max_length": max_length}
            )

        return value.strip()

    def validate_file_number(self, value):
        """Validate file_number field."""
        settings = self._get_validation_settings()
        min_length = settings.get("file_number_min_length", 1)
        max_length = settings.get("file_number_max_length", 100)

        if not value or not value.strip():
            raise serializers.ValidationError(_("File number cannot be empty."))

        value = value.strip()
        if len(value) < min_length:
            raise serializers.ValidationError(
                _("File number must be at least %(min_length)s characters.")
                % {"min_length": min_length}
            )
        if len(value) > max_length:
            raise serializers.ValidationError(
                _("File number must not exceed %(max_length)s characters.")
                % {"max_length": max_length}
            )

        return value

    def validate_content(self, value):
        """Validate content field."""
        settings = self._get_validation_settings()
        min_length = settings.get("content_min_length", 10)
        max_length = settings.get("content_max_length", 10000000)

        if not value:
            raise serializers.ValidationError(_("Content cannot be empty."))

        if len(value) < min_length:
            raise serializers.ValidationError(
                _("Content must be at least %(min_length)s characters.")
                % {"min_length": min_length}
            )
        if len(value) > max_length:
            raise serializers.ValidationError(
                _("Content must not exceed %(max_length)s characters.")
                % {"max_length": max_length}
            )

        return value

    def validate_title(self, value):
        """Validate title field."""
        if not value:
            return value

        settings = self._get_validation_settings()
        max_length = settings.get("title_max_length", 255)

        if len(value) > max_length:
            raise serializers.ValidationError(
                _("Title must not exceed %(max_length)s characters.")
                % {"max_length": max_length}
            )

        return value

    def validate_abstract(self, value):
        """Validate abstract field."""
        if not value:
            return value

        settings = self._get_validation_settings()
        max_length = settings.get("abstract_max_length", 50000)

        if len(value) > max_length:
            raise serializers.ValidationError(
                _("Abstract must not exceed %(max_length)s characters.")
                % {"max_length": max_length}
            )

        return value

    def validate_source(self, value):
        """Validate source field."""
        if not value:
            return value

        name = value.get("name", "")
        if not name or not name.strip():
            raise serializers.ValidationError(
                {"name": _("Source name cannot be empty.")}
            )

        if len(name) > 100:
            raise serializers.ValidationError(
                {"name": _("Source name must not exceed 100 characters.")}
            )

        value["name"] = name.strip()
        return value


class CaseCreateResponseSerializer(serializers.Serializer):
    """Serializer for case creation response."""

    id = serializers.IntegerField(help_text="Case ID")
    slug = serializers.CharField(help_text="Case slug for URL")
    review_status = serializers.CharField(help_text="Review status of the case")
