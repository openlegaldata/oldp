import coreapi
import coreschema
from rest_framework.filters import BaseFilterBackend


class SearchSchemaFilter(BaseFilterBackend):
    """
    This class add search index filters (facets) as parameters to the schema. If not used, generate swagger API clients
    do not support these parameters.
    """
    search_index_class = None

    def get_default_schema_fields(self):
        """
        Returns default fields as list. Usually text query field.
        """
        raise NotImplementedError()

    def get_schema_fields(self, view):
        fields = self.get_default_schema_fields()

        for field_name in self.search_index_class.fields:
            field = self.search_index_class.fields[field_name]

            if field.faceted:
                fields.append(
                    coreapi.Field(
                        name=field_name,
                        location='query',
                        required=False,
                        schema=coreschema.String(description=field_name),
                    ))

        return fields

    def filter_queryset(self, request, queryset, view):
        """
        Filter by model name
        """
        return queryset.filter(facet_model_name_exact=self.search_index_class.FACET_MODEL_NAME)
