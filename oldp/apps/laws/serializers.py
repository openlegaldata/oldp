from drf_haystack.serializers import HaystackSerializer
from rest_framework import serializers

from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.search_indexes import LawIndex


class LawSerializer(serializers.ModelSerializer):
    class Meta:
        model = Law
        fields = ('id', 'book', 'title', 'content', 'slug', 'created_date', 'updated_date', 'section', 'amtabk', 'kurzue', 'doknr', 'order')
        # depth = 2


class LawBookSerializer(serializers.ModelSerializer):
    class Meta:
        model = LawBook
        fields = ('id', 'code', 'slug', 'title', 'revision_date', 'latest', 'order')


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
