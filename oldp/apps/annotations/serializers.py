from django.core.exceptions import ValidationError
from rest_framework import serializers

from oldp.apps.annotations.models import AnnotationLabel, CaseAnnotation, CaseMarker
from oldp.apps.cases.models import Case


class AnnotationLabelSerializer(serializers.ModelSerializer):
    owner = serializers.ReadOnlyField(source="owner.username")
    trusted = serializers.ReadOnlyField()

    class Meta:
        model = AnnotationLabel
        fields = "__all__"
        unique_together = (
            "slug",
            "owner",
        )

    def validate(self, attrs):
        instance = AnnotationLabel(**attrs)
        instance.clean()

        return attrs


class CaseAnnotationSerializer(serializers.ModelSerializer):
    belongs_to = serializers.PrimaryKeyRelatedField(
        queryset=Case.get_queryset()
        .defer(*Case.defer_fields_list_view)
        .select_related("court"),
        html_cutoff=10,
    )
    label = serializers.PrimaryKeyRelatedField(
        queryset=AnnotationLabel.objects.all().select_related("owner"),
        html_cutoff=10,
    )

    class Meta:
        model = CaseAnnotation
        fields = "__all__"

    def validate_label(self, label):
        """Reject labels the requester does not own.

        ``Annotation.get_owner()`` returns ``self.label.owner``, so the label
        chosen here decides who the annotation *belongs to*. Without this check
        any authenticated user could post an annotation against another user's
        label and have it attributed to them -- appearing to the victim, and to
        staff, as the victim's own entry, consuming their per-label constraints
        and polluting their private namespace.

        ``OwnerPrivatePermission`` does not cover this: DRF only calls
        ``has_object_permission`` for an existing object, so on create the only
        gate was ``is_authenticated``.

        Ownership, not privacy, is the test. Allowing *public* labels owned by
        someone else would leave the hole open, because the annotation would
        still be attributed to that owner.

        Staff keep their existing reach, matching ``filter_queryset_by_permission``
        on the viewsets, so moderation tooling is unaffected.
        """
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if user is None or not user.is_authenticated:
            raise serializers.ValidationError(
                "Authentication is required to select an annotation label."
            )
        if user.is_staff:
            return label
        if label.owner_id != user.pk:
            raise serializers.ValidationError(
                "You can only use annotation labels that you own."
            )
        return label

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
        fields = "__all__"
