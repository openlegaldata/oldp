import logging

from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils.text import slugify

logger = logging.getLogger(__name__)


class Topic(models.Model):
    title = models.CharField(
        max_length=200,
        help_text='Verbose title of topic',
        unique=True,
    )
    slug = models.SlugField(
        max_length=200,
        help_text='Slug based on title',
        unique=True,
        blank=True,
        db_index=True,
    )
    created_date = models.DateTimeField(
        auto_now_add=True,
        help_text='Date of creation of this database entry'
    )
    updated_date = models.DateTimeField(
        auto_now=True,
        help_text='Last change of database entry'
    )

    def __repr__(self):
        return '<Topic({})>'.format(self.title)

    def __str__(self):
        return self.title


@receiver(pre_save, sender=Topic)
def pre_save_topic(sender, instance: Topic, *args, **kwargs):
    if instance.slug is None or instance.slug == '':
        instance.slug = slugify(instance.title)


class TopicContent(models.Model):
    """Abstract for content models that can be assigned to topics (e.g. case, law)."""
    topics = models.ManyToManyField(
        Topic,
        help_text='Topics that are covered by this content',
        blank=True,
    )

    class Meta:
        abstract = True
