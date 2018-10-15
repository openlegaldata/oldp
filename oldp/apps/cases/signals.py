from django.db.models.signals import pre_save
from django.dispatch import receiver

from oldp.apps.cases.models import Case


@receiver(pre_save, sender=Case)
def pre_save_case(sender, instance: Case, *args, **kwargs):

    # Is private content?
    # logger.info('Determining if private: %s ' % instance)
    instance.private = 'jportal' in instance.source_url or 'juris' in instance.source_url

    if instance.slug is None or instance.slug == "":
        instance.set_slug()

