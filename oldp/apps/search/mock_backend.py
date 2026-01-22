"""Mock Elasticsearch backend for unit testing.

This backend stores documents in memory and provides basic search matching.
Used when MOCK_ES_TESTS=True to run ES tests without a real Elasticsearch instance.
"""

import logging
import re
from collections import defaultdict

from haystack.backends import BaseEngine, BaseSearchBackend, BaseSearchQuery
from haystack.models import SearchResult
from haystack.utils import get_identifier, get_model_ct

logger = logging.getLogger(__name__)


class MockElasticsearchBackend(BaseSearchBackend):
    """In-memory document storage and search backend for testing.

    Stores documents in a class-level dictionary so they persist across
    backend instances within a test run. Call reset() to clear between tests.
    """

    # Class-level storage for documents - persists across instances
    _documents = {}
    _document_count = 0

    def __init__(self, connection_alias, **connection_options):
        super().__init__(connection_alias, **connection_options)
        self.index_name = connection_options.get("INDEX_NAME", "test_index")

    @classmethod
    def reset(cls):
        """Clear all stored documents. Call this in test setUp()."""
        cls._documents = {}
        cls._document_count = 0
        logger.debug("MockElasticsearchBackend: Reset document storage")

    @classmethod
    def get_document_count(cls):
        """Return the number of indexed documents."""
        return cls._document_count

    def update(self, index, iterable, commit=True):
        """Index documents into memory storage.

        Args:
            index: The SearchIndex instance
            iterable: Objects to index
            commit: Ignored for mock backend
        """
        for obj in iterable:
            doc = index.full_prepare(obj)
            doc_id = get_identifier(obj)

            # Store the document with its prepared data
            self._documents[doc_id] = {
                "data": doc,
                "model": get_model_ct(obj),
                "pk": str(obj.pk),
                "object": obj,
            }
            MockElasticsearchBackend._document_count = len(self._documents)

        logger.debug(
            "MockElasticsearchBackend: Indexed %d documents (total: %d)",
            len(list(iterable)) if hasattr(iterable, "__len__") else "?",
            len(self._documents),
        )

    def remove(self, obj_or_string):
        """Remove a document from memory storage.

        Args:
            obj_or_string: Model instance or identifier string
        """
        if isinstance(obj_or_string, str):
            doc_id = obj_or_string
        else:
            doc_id = get_identifier(obj_or_string)

        if doc_id in self._documents:
            del self._documents[doc_id]
            MockElasticsearchBackend._document_count = len(self._documents)
            logger.debug("MockElasticsearchBackend: Removed document %s", doc_id)

    def clear(self, models=None, commit=True):
        """Clear documents from memory storage.

        Args:
            models: Optional list of models to clear. If None, clears all.
            commit: Ignored for mock backend
        """
        if models is None:
            self._documents.clear()
        else:
            model_cts = [get_model_ct(model) for model in models]
            docs_to_remove = [
                doc_id
                for doc_id, doc in self._documents.items()
                if doc["model"] in model_cts
            ]
            for doc_id in docs_to_remove:
                del self._documents[doc_id]

        MockElasticsearchBackend._document_count = len(self._documents)
        logger.debug(
            "MockElasticsearchBackend: Cleared documents (remaining: %d)",
            len(self._documents),
        )

    def search(
        self,
        query_string,
        sort_by=None,
        start_offset=0,
        end_offset=None,
        fields="",
        highlight=False,
        facets=None,
        date_facets=None,
        query_facets=None,
        narrow_queries=None,
        spelling_query=None,
        within=None,
        dwithin=None,
        distance_point=None,
        models=None,
        limit_to_registered_models=None,
        result_class=None,
        **kwargs,
    ):
        """Search documents in memory storage.

        Performs basic text matching: checks if query terms appear in document content.

        Returns:
            dict with 'results' (list of SearchResult) and 'hits' (int count)
        """
        if result_class is None:
            result_class = SearchResult

        results = []
        hits = 0

        # Handle match_all query
        if query_string == "*:*" or not query_string:
            matching_docs = list(self._documents.values())
        else:
            # Simple text search: check if query terms appear in document text fields
            matching_docs = self._match_documents(query_string, models)

        hits = len(matching_docs)

        # Apply pagination
        if end_offset is None:
            end_offset = len(matching_docs)
        paginated_docs = matching_docs[start_offset:end_offset]

        # Convert to SearchResult objects
        for doc in paginated_docs:
            result = result_class(
                app_label=doc["model"].split(".")[0],
                model_name=doc["model"].split(".")[1],
                pk=doc["pk"],
                score=1.0,
            )
            # Add stored fields
            for key, value in doc["data"].items():
                setattr(result, key, value)
            results.append(result)

        # Build facet counts if requested
        facet_counts = {}
        if facets:
            facet_counts = self._build_facet_counts(facets, matching_docs)

        return {
            "results": results,
            "hits": hits,
            "facets": facet_counts,
            "spelling_suggestion": None,
        }

    def _match_documents(self, query_string, models=None):
        """Find documents matching the query string.

        Args:
            query_string: Search query
            models: Optional set of model classes to filter by

        Returns:
            List of matching document dicts
        """
        # Parse query terms (simple space-separated)
        # Remove Lucene operators for simple matching
        query_clean = re.sub(
            r"\b(AND|OR|NOT)\b", " ", query_string, flags=re.IGNORECASE
        )
        query_clean = re.sub(r'[:\(\)\[\]\{\}"\'\\]', " ", query_clean)
        terms = [t.lower().strip() for t in query_clean.split() if t.strip()]

        if not terms:
            return list(self._documents.values())

        matching = []
        model_cts = None
        if models:
            model_cts = {get_model_ct(model) for model in models}

        for doc_id, doc in self._documents.items():
            # Filter by model if specified
            if model_cts and doc["model"] not in model_cts:
                continue

            # Check if any term matches any text field
            doc_text = self._get_document_text(doc["data"]).lower()
            if any(term in doc_text for term in terms):
                matching.append(doc)

        return matching

    def _get_document_text(self, doc_data):
        """Extract searchable text from document data.

        Args:
            doc_data: Prepared document dict

        Returns:
            Concatenated string of all text fields
        """
        text_parts = []
        for key, value in doc_data.items():
            if isinstance(value, str):
                text_parts.append(value)
            elif isinstance(value, (list, tuple)):
                text_parts.extend(str(v) for v in value if v)
        return " ".join(text_parts)

    def _build_facet_counts(self, facets, matching_docs):
        """Build facet counts from matching documents.

        Args:
            facets: Dict of facet field names and options
            matching_docs: List of matching document dicts

        Returns:
            Dict with 'fields' containing facet counts
        """
        facet_counts = {"fields": {}, "dates": {}, "queries": {}}

        for facet_field in facets.keys():
            counts = defaultdict(int)
            # Look for the field in document data
            # Haystack typically stores facet fields with _exact suffix
            field_variants = [
                facet_field,
                f"{facet_field}_exact",
                f"facet_{facet_field}",
            ]

            for doc in matching_docs:
                for field_name in field_variants:
                    if field_name in doc["data"]:
                        value = doc["data"][field_name]
                        if value:
                            if isinstance(value, (list, tuple)):
                                for v in value:
                                    counts[str(v)] += 1
                            else:
                                counts[str(value)] += 1
                        break

            # Convert to list of tuples (value, count)
            facet_counts["fields"][facet_field] = sorted(
                counts.items(), key=lambda x: -x[1]
            )

        return facet_counts

    def build_search_kwargs(
        self,
        query_string,
        sort_by=None,
        start_offset=0,
        end_offset=None,
        fields="",
        highlight=False,
        facets=None,
        date_facets=None,
        query_facets=None,
        narrow_queries=None,
        spelling_query=None,
        within=None,
        dwithin=None,
        distance_point=None,
        models=None,
        limit_to_registered_models=None,
        result_class=None,
        **extra_kwargs,
    ):
        """Build search kwargs dict. For mock backend, just passes through."""
        return {
            "query_string": query_string,
            "sort_by": sort_by,
            "start_offset": start_offset,
            "end_offset": end_offset,
            "fields": fields,
            "highlight": highlight,
            "facets": facets,
            "date_facets": date_facets,
            "query_facets": query_facets,
            "narrow_queries": narrow_queries,
            "spelling_query": spelling_query,
            "models": models,
            "result_class": result_class,
        }

    def more_like_this(
        self, model_instance, additional_query_string=None, result_class=None, **kwargs
    ):
        """Find similar documents. Returns empty results for mock."""
        return {"results": [], "hits": 0}

    def build_schema(self, fields):
        """Build schema from fields. Returns simple structure for mock."""
        content_field_name = ""
        mapping = {}

        for field_name, field_class in fields.items():
            mapping[field_name] = {"type": "text"}
            if field_class.document is True:
                content_field_name = field_name

        return (content_field_name, mapping)

    def extract_file_contents(self, file_obj):
        """Extract file contents. Not supported in mock backend."""
        return None


class MockElasticsearchQuery(BaseSearchQuery):
    """Simple query building for mock backend.

    Extends BaseSearchQuery to provide basic query string building.
    """

    def build_query_fragment(self, field, filter_type, value):
        """Build a query fragment string.

        Args:
            field: Field name
            filter_type: Filter type (exact, contains, etc.)
            value: Search value

        Returns:
            Query string fragment
        """
        from haystack.inputs import Clean, Exact, Raw

        if isinstance(value, str):
            query_value = value
        elif isinstance(value, (Clean, Exact)):
            query_value = str(value)
        elif isinstance(value, Raw):
            query_value = value.query_string
        else:
            query_value = str(value)

        if field == "content":
            return query_value
        return f"{field}:{query_value}"

    def build_query(self):
        """Build the full query string."""
        if not self.query_filter:
            return "*:*"

        return self.query_filter.as_query_string(self.build_query_fragment)

    def clean(self, query_fragment):
        """Clean a query fragment. For mock, minimal cleaning."""
        if not query_fragment:
            return ""
        return str(query_fragment)


class MockElasticsearchEngine(BaseEngine):
    """Engine wrapper for mock Elasticsearch backend."""

    backend = MockElasticsearchBackend
    query = MockElasticsearchQuery
