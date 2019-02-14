from drf_haystack.serializers import HaystackSerializer
from rest_framework import serializers

from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.search_indexes import LawIndex


class LawSerializer(serializers.ModelSerializer):
    class Meta:
        model = Law
        fields = ('book', 'title', 'content', 'slug')
        # depth = 2


class LawBookSerializer(serializers.ModelSerializer):
    class Meta:
        model = LawBook
        fields = ('code', 'title', 'revision_date', 'latest')


class LawSearchSerializer(HaystackSerializer):
    id = serializers.SerializerMethodField()

    def get_id(self, obj):
        return int(obj.pk)

    class Meta:
        fields = [
            'book_code', 'title', 'text',
        ]
        field_options = {
            'book_code',
        }
        index_classes = [
            LawIndex
        ]
