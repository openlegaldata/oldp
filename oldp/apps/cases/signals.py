from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from oldp.apps.cases.models import Case
from oldp.apps.cases.search import CaseIndex


@receiver(pre_save, sender=Case)
def pre_save_case(sender, instance: Case, *args, **kwargs):

    # Is private content?
    # logger.info('Determining if private: %s ' % instance)
    instance.private = 'jportal' in instance.source_url or 'juris' in instance.source_url

    if instance.slug is None or instance.slug == "":
        instance.set_slug()


@receiver(post_save, sender=Case)
def post_save_case(sender, instance: Case, created, *args, **kwargs):
    pass
