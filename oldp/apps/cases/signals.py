from django.db.models.signals import pre_save
from django.dispatch import receiver

from oldp.apps.cases.models import Case


@receiver(pre_save, sender=Case)
def pre_save_case(sender, instance: Case, *args, **kwargs):

    if instance.slug is None or instance.slug == "":
        instance.set_slug()

