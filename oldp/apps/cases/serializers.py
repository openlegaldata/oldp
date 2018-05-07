from rest_framework import serializers

from oldp.apps.cases.models import Case


class CaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Case
        fields = ('id', 'court_id', 'file_number', 'date', 'type', 'ecli', 'content')

