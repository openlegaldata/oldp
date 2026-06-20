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
    "source_url",
    "review_status",
)

CASE_API_LIST_FIELDS = tuple(f for f in CASE_API_FIELDS if f != "content")


class CaseSerializer(ReviewStatusFieldMixin, serializers.ModelSerializer):
    court = CourtMinimalSerializer(many=False, read_only=True)
    slug = serializers.ReadOnlyField()

    class Meta:
        model = Case
        fields = CASE_API_FIELDS

        lookup_field = "slug"


class CaseListSerializer(ReviewStatusFieldMixin, serializers.ModelSerializer):
    """Serializer for case list views, excluding the large content field."""

    court = CourtMinimalSerializer(many=False, read_only=True)
    slug = serializers.ReadOnlyField()

    class Meta:
        model = Case
        fields = CASE_API_LIST_FIELDS
        lookup_field = "slug"


class CaseSearchSerializer(SearchResultSerializer):
    """Serializer for case search results."""

    # Haystack stores doc ids as strings (ES doc-id convention), so
    # ``result.pk`` arrives here as a string. Cast to int — the Case
    # Django PK is the source of truth and downstream consumers
    # (e.g. the MCP ``get_case`` tool, generic clients that follow up
    # with ``/api/cases/<id>/``) want an int. Mirrors the same fix on
    # ``LawSearchSerializer`` and the MCP ``search_cases`` tool.
    id = serializers.SerializerMethodField()
    # Declared (not auto-added as CharField) so it serializes as an int.
    citing_cases_count = serializers.IntegerField(read_only=True, default=0)
    # Normalize the placeholder "unknown" court code to null so REST consumers
    # branch on a real null instead of mistaking "unknown" for an actual court
    # — parity with the MCP ``search_cases`` tool, which already does this via
    # ``_norm_court``. Declaring it here keeps it out of the __init__
    # auto-CharField path; ``SearchResultSerializer.to_representation`` honours
    # SerializerMethodField.
    court = serializers.SerializerMethodField()

    def get_id(self, obj):
        return int(obj.pk)

    def get_court(self, obj):
        # Reuse the single normalization definition (placeholder "unknown" →
        # None). Lazy import avoids loading the MCP module at serializer
        # import time.
        from oldp.apps.cases.mcp import _norm_court

        return _norm_court(getattr(obj, "court", None))

    class Meta:
        fields = [
            "slug",
            "date",
            "text",
            "court",
            "court_jurisdiction",
            "court_level_of_appeal",
            "decision_type",
            # Reverse-citation count, so API consumers can see the basis of
            # the order_by=most_cited sort (mirrors the MCP search_cases tool).
            "citing_cases_count",
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
    source_url = serializers.URLField(
        required=False,
        allow_blank=True,
        default="",
        help_text="URL the case content was extracted from (PDF, HTML detail page, API endpoint, ZIP, etc.).",
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


class CaseUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating cases via PATCH. Only review_status is writable."""

    class Meta:
        model = Case
        fields = ("review_status",)

    def validate_review_status(self, value):
        if value not in ("pending", "accepted", "rejected"):
            raise serializers.ValidationError(
                f"Invalid review_status: {value}. Must be pending, accepted, or rejected."
            )
        return value


class CaseCreateResponseSerializer(serializers.Serializer):
    """Serializer for case creation response."""

    id = serializers.IntegerField(help_text="Case ID")
    slug = serializers.CharField(help_text="Case slug for URL")
    review_status = serializers.CharField(help_text="Review status of the case")
