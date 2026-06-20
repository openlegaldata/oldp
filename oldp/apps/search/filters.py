from rest_framework.filters import BaseFilterBackend

from oldp.apps.search.utils import narrow_to_model


class SearchSchemaFilter(BaseFilterBackend):
    """This class add search index filters (facets) as parameters to the schema. If not used, generate swagger API clients
    do not support these parameters.
    """

    search_index_class = None

    def get_default_schema_operation_parameters(self):
        """Returns default parameters as list. Usually text query field."""
        raise NotImplementedError()

    def get_schema_operation_parameters(self, view):
        params = self.get_default_schema_operation_parameters()

        for field_name in self.search_index_class.fields:
            field = self.search_index_class.fields[field_name]

            if field.faceted:
                params.append(
                    {
                        "name": field_name,
                        "required": False,
                        "in": "query",
                        "description": field_name,
                        "schema": {"type": "string"},
                    }
                )

        return params

    def filter_queryset(self, request, queryset, view):
        """Filter by model name and apply user-specified facet filters.

        Always applies the model name facet filter, then checks query parameters
        for any additional faceted fields defined on the search index and applies
        those as well. This allows API consumers to replicate the same facet-based
        filtering available in the web search UI.
        """
        # Filter-context narrow (not .filter) so the clamp stays out of the
        # scoring query string — keeps short navigational lookups eligible
        # for the exact-match boost and prevents the boost leaking the other
        # model. See ``narrow_to_model``.
        queryset = narrow_to_model(queryset, self.search_index_class.FACET_MODEL_NAME)

        for field_name, field in self.search_index_class.fields.items():
            if not field.faceted:
                continue
            if field_name == "facet_model_name":
                continue
            value = request.query_params.get(field_name, "").strip()
            if value:
                queryset = queryset.filter(**{f"{field_name}_exact": value})

        return queryset
