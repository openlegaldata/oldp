from django.conf import settings as django_settings
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from oldp.api.mixins import ReviewStatusFieldMixin
from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.search_indexes import LawIndex
from oldp.apps.search.api import SearchResultSerializer


class LawSerializer(ReviewStatusFieldMixin, serializers.ModelSerializer):
    class Meta:
        model = Law
        fields = (
            "id",
            "book",
            "title",
            "content",
            "slug",
            "created_date",
            "updated_date",
            "section",
            "amtabk",
            "kurzue",
            "doknr",
            "order",
            "review_status",
        )
        # depth = 2


class LawBookSerializer(ReviewStatusFieldMixin, serializers.ModelSerializer):
    class Meta:
        model = LawBook
        fields = (
            "id",
            "code",
            "slug",
            "title",
            "revision_date",
            "latest",
            "order",
            "review_status",
        )


class LawSearchSerializer(SearchResultSerializer):
    """Serializer for law search results."""

    id = serializers.SerializerMethodField()

    def get_id(self, obj):
        return int(obj.pk)

    class Meta:
        fields = [
            "book_code",
            "title",
            "text",
        ]
        index_classes = [LawIndex]


# ============================================================================
# Creation Serializers
# ============================================================================


class LawBookCreateSerializer(serializers.Serializer):
    """Serializer for creating law books via API.

    Handles automatic revision management.
    """

    # Required fields
    code = serializers.CharField(
        max_length=100, help_text="Book code (e.g., 'BGB', 'StGB')"
    )
    title = serializers.CharField(max_length=250, help_text="Full title of the book")
    revision_date = serializers.DateField(
        help_text="Date of this revision (YYYY-MM-DD format)"
    )

    # Optional fields
    order = serializers.IntegerField(
        default=0, min_value=0, help_text="Display order (importance)"
    )
    changelog = serializers.CharField(
        required=False, allow_blank=True, help_text="Changelog as JSON array"
    )
    footnotes = serializers.CharField(
        required=False, allow_blank=True, help_text="Footnotes as JSON array"
    )
    sections = serializers.CharField(
        required=False, allow_blank=True, help_text="Sections as JSON object"
    )

    def validate_code(self, value):
        """Validate book code."""
        if not value or not value.strip():
            raise serializers.ValidationError(_("Book code cannot be empty."))
        return value.strip()

    def validate_title(self, value):
        """Validate book title."""
        if not value or not value.strip():
            raise serializers.ValidationError(_("Book title cannot be empty."))
        return value.strip()


class LawBookCreateResponseSerializer(serializers.Serializer):
    """Serializer for law book creation response."""

    id = serializers.IntegerField(help_text="Law book ID")
    slug = serializers.CharField(help_text="Law book slug")
    latest = serializers.BooleanField(help_text="Whether this is the latest revision")
    review_status = serializers.CharField(help_text="Review status of the law book")


class LawCreateSerializer(serializers.Serializer):
    """Serializer for creating laws via API.

    Accepts book_code instead of book FK, with automatic resolution.
    """

    # Required fields
    book_code = serializers.CharField(
        max_length=100, help_text="Law book code (e.g., 'BGB', 'StGB')"
    )
    section = serializers.CharField(
        max_length=200, help_text="Section identifier (e.g., '§ 1', 'Art. 1')"
    )
    title = serializers.CharField(max_length=200, help_text="Verbose title of the law")
    content = serializers.CharField(help_text="Law content in HTML format")

    # Optional fields
    revision_date = serializers.DateField(
        required=False,
        help_text="Specific book revision date (uses latest if not specified)",
    )
    slug = serializers.SlugField(
        required=False,
        max_length=200,
        help_text="Law slug (auto-generated from section if not provided)",
    )
    order = serializers.IntegerField(
        default=0, min_value=0, help_text="Order within the book"
    )
    amtabk = serializers.CharField(
        required=False,
        max_length=200,
        allow_blank=True,
        help_text="Official abbreviation",
    )
    kurzue = serializers.CharField(
        required=False, max_length=200, allow_blank=True, help_text="Short title"
    )
    doknr = serializers.CharField(
        required=False,
        max_length=200,
        allow_blank=True,
        help_text="Document number from XML source",
    )
    footnotes = serializers.CharField(
        required=False, allow_blank=True, help_text="Footnotes as JSON array"
    )

    def _get_validation_settings(self):
        """Get validation settings with defaults."""
        defaults = {
            "content_min_length": 1,
            "content_max_length": 10000000,
        }
        settings = getattr(django_settings, "LAW_CREATION_VALIDATION", {})
        return {**defaults, **settings}

    def validate_book_code(self, value):
        """Validate book code."""
        if not value or not value.strip():
            raise serializers.ValidationError(_("Book code cannot be empty."))
        return value.strip()

    def validate_section(self, value):
        """Validate section."""
        if not value or not value.strip():
            raise serializers.ValidationError(_("Section cannot be empty."))
        return value.strip()

    def validate_content(self, value):
        """Validate content field."""
        settings = self._get_validation_settings()
        min_length = settings.get("content_min_length", 1)
        max_length = settings.get("content_max_length", 10000000)

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


class LawCreateResponseSerializer(serializers.Serializer):
    """Serializer for law creation response."""

    id = serializers.IntegerField(help_text="Law ID")
    slug = serializers.CharField(help_text="Law slug")
    book_id = serializers.IntegerField(help_text="Law book ID")
    review_status = serializers.CharField(help_text="Review status of the law")
