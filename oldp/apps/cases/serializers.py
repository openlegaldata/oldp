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

    def get_id(self, obj):
        return int(obj.pk)

    class Meta:
        fields = [
            'slug', 'date', 'text', 'court', 'court_jurisdiction', 'court_level_of_appeal', 'decision_type',
        ]
        field_options = {
            'court': {},
            'court_jurisdiction': {},
            'court_level_of_appeal': {},
            'decision_type': {},
            'date': {}
        }
        index_classes = [
            CaseIndex
        ]
