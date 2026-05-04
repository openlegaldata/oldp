"""Shared mixins for API viewsets and serializers.

Provides review_status-based filtering and field visibility control.
"""

from django.db.models import Q


def filter_by_review_status(qs, request):
    """Restrict ``qs`` by ``review_status`` according to the request's user.

    - Staff: full queryset
    - Authenticated non-staff: accepted items plus items they created
      (matched via ``created_by_token__user``)
    - Anonymous, no request, or request without a user: accepted only

    Used by :class:`ReviewStatusFilterMixin` for DRF viewsets and by the
    ``Case.get_queryset`` / ``Law.get_queryset`` / ``LawBook.get_queryset``
    static methods so all entry points share one rule.
    """
    if request is None or not hasattr(request, "user"):
        return qs.filter(review_status="accepted")

    user = request.user

    if user.is_authenticated and user.is_staff:
        return qs

    if user.is_authenticated:
        return qs.filter(Q(review_status="accepted") | Q(created_by_token__user=user))

    return qs.filter(review_status="accepted")


class ReviewStatusFilterMixin:
    """Filters queryset by review_status based on the authenticated user.

    Thin wrapper around :func:`filter_by_review_status` so DRF viewsets can
    drop it into their MRO without duplicating the rule.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        request = getattr(self, "request", None)
        return filter_by_review_status(qs, request)


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
