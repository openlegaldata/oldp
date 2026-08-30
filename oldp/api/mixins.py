"""Shared mixins for API viewsets and serializers.

Provides review_status-based filtering and field visibility control.
"""

from django.db.models import Q


def _own_token_ids(request, user) -> list[int]:
    """Ids of ``user``'s API tokens, memoised on the request.

    ``filter_by_review_status`` runs several times per request (DRF calls
    ``get_queryset`` for the list, the filter backend and the paginator), so
    resolve this once and hang it off the request.
    """
    cached = getattr(request, "_oldp_own_token_ids", None)
    if cached is not None:
        return cached

    # Local import: the accounts app imports from oldp.api, so a module-level
    # import here would close a cycle.
    from oldp.apps.accounts.models import APIToken

    token_ids = list(APIToken.objects.filter(user=user).values_list("id", flat=True))
    try:
        request._oldp_own_token_ids = token_ids
    except AttributeError:  # pragma: no cover - exotic request objects
        pass
    return token_ids


def filter_by_review_status(qs, request):
    """Restrict ``qs`` by ``review_status`` according to the request's user.

    - Staff: full queryset
    - Authenticated non-staff: accepted items plus items they created
    - Anonymous, no request, or request without a user: accepted only

    Used by :class:`ReviewStatusFilterMixin` for DRF viewsets and by the
    ``Case.get_queryset`` / ``Law.get_queryset`` / ``LawBook.get_queryset``
    static methods so all entry points share one rule.

    The own-content branch matches ``created_by_token_id`` against a
    materialised id list rather than traversing ``created_by_token__user``.
    That traversal put a ``LEFT OUTER JOIN accounts_apitoken`` inside an
    ``OR``, which the planner cannot trim -- and which survived into DRF's
    pagination ``COUNT(*)``, producing

        SELECT COUNT(*) FROM cases_case LEFT OUTER JOIN accounts_apitoken ...

    at ~4.3s and 585k rows examined per call in the prod slow log
    (internal-tools#5). A user has a handful of tokens, so the id list is tiny
    and the extra lookup is an indexed hit on a small table -- the same
    materialise-then-``IN`` shape the citation-graph helpers already use to
    keep MariaDB on a sane plan.
    """
    if request is None or not hasattr(request, "user"):
        return qs.filter(review_status="accepted")

    user = request.user

    if user.is_authenticated and user.is_staff:
        return qs

    if user.is_authenticated:
        token_ids = _own_token_ids(request, user)
        if not token_ids:
            # No tokens -> the OR branch can never match. Skip it rather than
            # emitting an empty IN ().
            return qs.filter(review_status="accepted")
        return qs.filter(
            Q(review_status="accepted") | Q(created_by_token_id__in=token_ids)
        )

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
