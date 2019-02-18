from django.core.exceptions import ValidationError
from rest_framework import serializers

from oldp.apps.annotations.models import AnnotationLabel, CaseAnnotation, CaseMarker
from oldp.apps.cases.models import Case


class AnnotationLabelSerializer(serializers.ModelSerializer):
    owner = serializers.ReadOnlyField(
        source='owner.username'
    )
    trusted = serializers.ReadOnlyField()

    class Meta:
        model = AnnotationLabel
        fields = '__all__'
        unique_together = (
            ('slug', 'owner',)
        )

    def validate(self, attrs):
        instance = AnnotationLabel(**attrs)
        instance.clean()

        return attrs


class CaseAnnotationSerializer(serializers.ModelSerializer):
    belongs_to = serializers.PrimaryKeyRelatedField(
        queryset=Case.get_queryset().defer(*Case.defer_fields_list_view).select_related('court'),
        html_cutoff=10,
    )
    label = serializers.PrimaryKeyRelatedField(
        queryset=AnnotationLabel.objects.all().select_related('owner'),
        html_cutoff=10,
    )

    class Meta:
        model = CaseAnnotation
        fields = '__all__'

    def validate(self, attrs):
        instance = self.Meta.model(**attrs)

        # Work-around to show fields in error response
        try:
            instance.clean()
        except ValidationError as e:
            raise serializers.ValidationError(e.args[0])

        return attrs


class CaseMarkerSerializer(CaseAnnotationSerializer):
    class Meta:
        model = CaseMarker
        fields = '__all__'
