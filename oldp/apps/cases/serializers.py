from drf_haystack.serializers import HaystackSerializer
from rest_framework import serializers

from oldp.apps.cases.models import Case
from oldp.apps.cases.search_indexes import CaseIndex
from oldp.apps.courts.serializers import CourtMinimalSerializer

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
)


class CaseSerializer(serializers.ModelSerializer):
    court = CourtMinimalSerializer(many=False, read_only=True)
    slug = serializers.ReadOnlyField()

    class Meta:
        model = Case
        fields = CASE_API_FIELDS

        lookup_field = "slug"


class CaseSearchSerializer(HaystackSerializer):
    """This search does not support any faceting!

    See https://drf-haystack.readthedocs.io/en/latest/07_faceting.html
    """

    class Meta:
        fields = [
            "slug",
            "date",
            "text",
            "court",
            "court_jurisdiction",
            "court_level_of_appeal",
            "decision_type",
        ]
        index_classes = [CaseIndex]
