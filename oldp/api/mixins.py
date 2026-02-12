"""Shared mixins for API viewsets and serializers.

Provides review_status-based filtering and field visibility control.
"""

from django.db.models import Q


class ReviewStatusFilterMixin:
    """Filters queryset by review_status based on the authenticated user.

    - Staff: see all items
    - Authenticated non-staff: see accepted + items created by their token
    - Unauthenticated: see only accepted items
    """

    def get_queryset(self):
        qs = super().get_queryset()

        if not hasattr(self, "request") or self.request is None:
            return qs.filter(review_status="accepted")

        user = self.request.user

        if user.is_authenticated and user.is_staff:
            return qs

        if user.is_authenticated:
            return qs.filter(
                Q(review_status="accepted") | Q(created_by_token__user=user)
            )

        return qs.filter(review_status="accepted")


class ReviewStatusFieldMixin:
    """Conditionally includes review_status in serialized output.

    Shows review_status only to staff users and the item's creator.
    Requires select_related("created_by_token") on the queryset for efficiency.
    """

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        show = False

        if request and hasattr(request, "user"):
            user = request.user
            if user.is_authenticated:
                if user.is_staff:
                    show = True
                elif (
                    instance.created_by_token_id
                    and instance.created_by_token.user_id == user.pk
                ):
                    show = True

        if not show:
            data.pop("review_status", None)

        return data
