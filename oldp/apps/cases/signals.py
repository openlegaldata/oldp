import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from haystack import connection_router, connections
from haystack.exceptions import NotHandled

from oldp.apps.cases.cache import invalidate_case_cache
from oldp.apps.cases.models import Case

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Case)
def pre_save_case(sender, instance: Case, *args, **kwargs):
    if instance.slug is None or instance.slug == "":
        instance.set_slug()


@receiver(post_save, sender=Case)
def invalidate_case_detail_cache(sender, instance: Case, **kwargs):
    """Drop slug-keyed view-cache entries whenever a case is saved.

    The case detail view caches under slug-only keys. Any save (especially
    a `review_status` transition) might change what should be served, so
    we invalidate unconditionally — cheaper than tracking the prior value
    and correct under demotion (accepted -> pending) as well as
    promotion.
    """
    if instance.slug:
        invalidate_case_cache(instance.slug)


def _sync_case_to_search_index(instance: Case) -> None:
    """Mirror the case's review_status to the ES search index.

    ``CaseIndex.index_queryset`` only emits ``review_status='accepted'``
    rows (via ``Case.get_queryset``), so the index is correct for
    accepted cases — but when a case is demoted (accepted → pending or
    rejected) the existing ES doc is never removed. ``update_index``
    upserts; it doesn't reconcile. Without this hook the index drifts
    until the next ``scripts/prune_stale_es_docs.sh`` run.

    Promotions (any → accepted) are likewise covered: ``update_object``
    upserts a fresh doc on transition into the indexable state.
    """
    using_backends = connection_router.for_write(instance=instance)
    for using in using_backends:
        try:
            index = connections[using].get_unified_index().get_index(Case)
        except NotHandled:
            continue
        try:
            if instance.review_status == "accepted":
                index.update_object(instance, using=using)
            else:
                index.remove_object(instance, using=using)
        except Exception:
            # ES outages must not break Case.save() callers; the index
            # is rebuildable from the DB via ``update_index cases``.
            logger.exception(
                "search-index sync failed for case pk=%s using=%s",
                instance.pk,
                using,
            )


@receiver(post_save, sender=Case)
def sync_case_to_search_index_on_save(
    sender, instance: Case, raw: bool = False, **kwargs
):
    """Keep ES in sync with ``review_status`` transitions on every save.

    Deferred to ``transaction.on_commit`` so a rolled-back save does
    not leak into ES, and so bulk-save callers inside a transaction
    coalesce naturally.
    """
    if raw:
        # Loading fixtures — skip ES writes; ``loaddata`` is followed
        # by an explicit ``update_index`` in our deploy flow.
        return
    transaction.on_commit(lambda: _sync_case_to_search_index(instance))


@receiver(post_delete, sender=Case)
def remove_case_from_search_index_on_delete(sender, instance: Case, **kwargs):
    """Hard-deletes never leave residue in the index."""
    transaction.on_commit(lambda: _sync_case_to_search_index_remove(instance))


def _sync_case_to_search_index_remove(instance: Case) -> None:
    using_backends = connection_router.for_write(instance=instance)
    for using in using_backends:
        try:
            index = connections[using].get_unified_index().get_index(Case)
            index.remove_object(instance, using=using)
        except NotHandled:
            continue
        except Exception:
            logger.exception(
                "search-index removal failed for case pk=%s using=%s",
                instance.pk,
                using,
            )
