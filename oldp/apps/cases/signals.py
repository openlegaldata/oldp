from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from oldp.apps.cases.cache import invalidate_case_cache
from oldp.apps.cases.models import Case


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
