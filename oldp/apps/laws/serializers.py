from rest_framework import serializers

from oldp.apps.laws.models import Law, LawBook


class LawSerializer(serializers.ModelSerializer):
    class Meta:
        model = Law
        fields = ('book', 'title', 'text', 'slug')
        # depth = 2


class LawBookSerializer(serializers.ModelSerializer):
    class Meta:
        model = LawBook
        fields = ('code', 'title', 'revision_date', 'latest')

