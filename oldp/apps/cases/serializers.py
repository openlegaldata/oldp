from rest_framework import serializers

from oldp.apps.cases.models import Case
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
