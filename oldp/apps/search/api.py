"""Search API components for DRF.

Provides integration between Django REST Framework and django-haystack:
- SearchQueryBuilder: Shared query construction for web and API search
- SearchResultSerializer: Serializer for search results with snippet support
- SearchViewMixin: Mixin for views that query the search backend
- SearchFilter: Filter backend for search queries
"""

import datetime
import logging
import re

from django.conf import settings
from haystack.query import SearchQuerySet
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.filters import BaseFilterBackend

from oldp.apps.search.exceptions import (
    SearchBackendTimeout,
    SearchBackendUnavailable,
)
from oldp.apps.search.utils import (
    is_search_backend_error,
    is_search_backend_timeout,
)

logger = logging.getLogger(__name__)


class SearchQueryBuilder:
    """Builds a SearchQuerySet with shared logic for both web and API paths.

    Consolidates highlighting, date range filtering, and review_status filtering
    that were previously duplicated between CustomSearchView and SearchViewMixin.
    """

    def __init__(self, queryset=None):
        self.queryset = queryset or SearchQuerySet()

    def filter_models(self, models):
        """Filter by model classes."""
        if models:
            self.queryset = self.queryset.models(*models)
        return self

    def filter_review_status(self, status="accepted"):
        """Filter by review_status."""
        self.queryset = self.queryset.filter(review_status=status)
        return self

    def apply_highlight(self):
        """Enable ES highlighting on the queryset."""
        max_snippets = getattr(settings, "SEARCH_MAX_SNIPPETS", 3)
        snippet_size = getattr(settings, "SEARCH_SNIPPET_SIZE", 200)
        self.queryset = self.queryset.highlight(
            number_of_fragments=max_snippets,
            fragment_size=snippet_size,
        )
        return self

    def apply_date_range(self, start_date_str, end_date_str):
        """Apply date range filtering from string parameters.

        Args:
            start_date_str: Date string in YYYY-MM-DD format, or empty/None.
            end_date_str: Date string in YYYY-MM-DD format, or empty/None.
        """
        if start_date_str:
            try:
                parsed = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
                self.queryset = self.queryset.filter(date__gte=parsed)
            except ValueError:
                logger.error("Invalid start_date: %s", start_date_str)
        if end_date_str:
            try:
                parsed = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")
                self.queryset = self.queryset.filter(date__lte=parsed)
            except ValueError:
                logger.error("Invalid end_date: %s", end_date_str)
        return self

    def build(self):
        """Return the constructed SearchQuerySet."""
        return self.queryset


def _strip_highlight_tags(fragment):
    """Strip <em> and </em> tags from an ES highlight fragment."""
    return re.sub(r"</?em>", "", fragment)


def _build_snippets(instance):
    """Build snippet dicts from a SearchResult's highlighted fragments.

    Each snippet contains:
        - text: The highlighted fragment (with <em> tags)
        - offset: Character position in the original text (-1 if not found)
        - length: Length of the plain-text fragment (without tags)

    Falls back to a truncated text snippet when no highlighting is available.
    """
    snippet_size = getattr(settings, "SEARCH_SNIPPET_SIZE", 200)
    full_text = getattr(instance, "text", "") or ""

    if hasattr(instance, "highlighted") and instance.highlighted:
        snippets = []
        for fragment in instance.highlighted:
            plain = _strip_highlight_tags(fragment)
            offset = full_text.find(plain) if full_text else -1
            snippets.append(
                {
                    "text": fragment,
                    "offset": offset,
                    "length": len(plain),
                }
            )
        return snippets

    # Fallback: truncated text
    truncated = full_text[:snippet_size]
    if len(full_text) > snippet_size:
        truncated += "..."
    return [{"text": truncated, "offset": 0, "length": len(truncated)}]


class SearchResultSerializer(serializers.Serializer):
    """Serializer for search results.

    By default returns snippets instead of full text. Use ?return_text=1
    to include the full text field as well.

    Configure via Meta class:
        - index_classes: List of SearchIndex classes
        - fields: List of field names to include in output
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        meta = getattr(self, "Meta", None)
        fields = getattr(meta, "fields", [])

        # Dynamically add fields from Meta.fields
        for field_name in fields:
            if field_name not in self.fields:
                self.fields[field_name] = serializers.CharField(
                    read_only=True, allow_null=True
                )

    def _should_return_text(self):
        """Check if full text was requested via return_text query param."""
        request = self.context.get("request")
        if request:
            return request.query_params.get("return_text", "") in ("1", "true")
        return False

    def to_representation(self, instance):
        """Convert SearchResult to dict.

        Replaces 'text' field with 'snippets' list by default.
        If return_text=1, includes both 'text' and 'snippets'.

        SerializerMethodField is honoured (its bound method runs against
        the SearchResult instance) so subclasses can transform fields —
        notably ``id`` from haystack's "laws.law.123" identifier string
        down to the bare integer Django PK. The naive
        ``getattr(instance, field_name)`` path used previously skipped
        DRF's field-resolution logic and returned the raw haystack
        identifier instead of whatever the method computed. Other
        explicitly-declared field types fall back to
        ``Field.to_representation`` after pulling the value via
        ``get_attribute``.
        """
        result = {}
        return_text = self._should_return_text()

        for field_name, field in self.fields.items():
            if field_name == "text":
                if return_text:
                    result["text"] = getattr(instance, "text", None)
                continue
            if isinstance(field, serializers.SerializerMethodField):
                method = getattr(self, field.method_name or f"get_{field_name}")
                result[field_name] = method(instance)
                continue
            # The auto-added CharField path (see __init__) plus anything
            # a subclass declares as a plain Field. We bypass
            # ``field.get_attribute`` because SearchResult attribute
            # access is dotted (no dict / nested traversal), and use
            # ``field.to_representation`` to honour the field's own
            # coercion (e.g. IntegerField casting).
            value = getattr(instance, field_name, None)
            result[field_name] = (
                field.to_representation(value) if value is not None else None
            )

        result["snippets"] = _build_snippets(instance)
        return result


class SearchFilter(BaseFilterBackend):
    """Filter backend that performs full-text search.

    Reads 'text' query parameter and runs search query.
    """

    def get_schema_operation_parameters(self, view):
        return [
            {
                "name": "start_date",
                "required": False,
                "in": "query",
                "description": "Filter results from this date (YYYY-MM-DD).",
                "schema": {"type": "string", "format": "date"},
            },
            {
                "name": "end_date",
                "required": False,
                "in": "query",
                "description": "Filter results up to this date (YYYY-MM-DD).",
                "schema": {"type": "string", "format": "date"},
            },
            {
                "name": "return_text",
                "required": False,
                "in": "query",
                "description": "Set to 1 to include full text in addition to snippets.",
                "schema": {"type": "string", "enum": ["0", "1"]},
            },
        ]

    def filter_queryset(self, request, queryset, view):
        """Filter queryset based on search text parameter.

        Args:
            request: The HTTP request.
            queryset: A SearchQuerySet to filter.
            view: The view being filtered.

        Returns:
            Filtered SearchQuerySet.
        """
        text = request.query_params.get("text", "").strip()

        if not text:
            raise ValidationError(
                {"text": "The 'text' query parameter is required for search."}
            )

        queryset = queryset.auto_query(text)

        # Apply model filter from view
        search_models = getattr(view, "search_models", [])
        if search_models:
            queryset = queryset.models(*search_models)

        return queryset


class SearchViewMixin:
    """Mixin for views that query the search backend.

    Provides get_queryset() that returns SearchQuerySet with highlighting
    and date range filtering via shared SearchQueryBuilder.
    Configure via:
        - search_models: List of model classes to search
    """

    search_models = []

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except Exception as exc:
            # Distinguish timeouts (retryable: warm-cache miss) from
            # true backend outages so REST callers can decide whether
            # to retry the same query vs. surface a hard failure.
            if is_search_backend_timeout(exc):
                raise SearchBackendTimeout() from exc
            if is_search_backend_error(exc):
                raise SearchBackendUnavailable() from exc
            raise

    def get_queryset(self):
        """Return a SearchQuerySet with highlighting and date range support."""
        builder = SearchQueryBuilder()
        builder.filter_models(self.search_models)
        builder.filter_review_status("accepted")
        builder.apply_highlight()

        # Apply date range from request params if available
        request = getattr(self, "request", None)
        if request:
            builder.apply_date_range(
                request.query_params.get("start_date", ""),
                request.query_params.get("end_date", ""),
            )

        return builder.build()
