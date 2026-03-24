"""Search API components for DRF.

Provides integration between Django REST Framework and django-haystack:
- SearchResultSerializer: Serializer for search results
- SearchViewMixin: Mixin for views that query the search backend
- SearchFilter: Filter backend for search queries
"""

from haystack.query import SearchQuerySet
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.filters import BaseFilterBackend

from oldp.apps.search.exceptions import SearchBackendUnavailable
from oldp.apps.search.utils import is_search_backend_error


class SearchResultSerializer(serializers.Serializer):
    """Serializer for search results.

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

    def to_representation(self, instance):
        """Convert SearchResult to dict."""
        result = {}
        for field_name in self.fields:
            value = getattr(instance, field_name, None)
            result[field_name] = value
        return result


class SearchFilter(BaseFilterBackend):
    """Filter backend that performs full-text search.

    Reads 'text' query parameter and runs search query.
    """

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

    Provides get_queryset() that returns SearchQuerySet.
    Configure via:
        - search_models: List of model classes to search
    """

    search_models = []

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except Exception as exc:
            if is_search_backend_error(exc):
                raise SearchBackendUnavailable() from exc
            raise

    def get_queryset(self):
        """Return a SearchQuerySet filtered by search_models and review_status."""
        sqs = SearchQuerySet()
        if self.search_models:
            sqs = sqs.models(*self.search_models)
        sqs = sqs.filter(review_status="accepted")
        return sqs
