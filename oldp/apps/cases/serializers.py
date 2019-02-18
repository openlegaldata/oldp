from drf_haystack.serializers import HaystackSerializer
from rest_framework import serializers

from oldp.apps.cases.models import Case
from oldp.apps.cases.search_indexes import CaseIndex
from oldp.apps.courts.serializers import CourtMinimalSerializer

CASE_API_FIELDS = ('id', 'slug', 'court', 'file_number', 'date', 'created_date', 'updated_date', 'type', 'ecli', 'content')


class CaseSerializer(serializers.ModelSerializer):
    court = CourtMinimalSerializer(many=False, read_only=True)
    slug = serializers.ReadOnlyField()

    class Meta:
        model = Case
        fields = CASE_API_FIELDS

        # lookup_field = 'slug'
        # extra_kwargs = {
        #     'url': {'lookup_field': 'slug'}
        # }


class CaseSearchSerializer(HaystackSerializer):
    id = serializers.SerializerMethodField()

    # Facet fields needs to be explicitly defined as not-required
    court_jurisdiction = serializers.ReadOnlyField(required=False)
    court_level_of_appeal = serializers.ReadOnlyField(required=False)
    decision_type = serializers.ReadOnlyField(required=False)

    def get_id(self, obj):
        return int(obj.pk)

    class Meta:
        fields = [
            'slug', 'date', 'text', 'court', 'court_jurisdiction', 'court_level_of_appeal', 'decision_type',
        ]
        index_classes = [
            CaseIndex
        ]
