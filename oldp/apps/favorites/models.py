from django.contrib.auth.models import User
from django.core.validators import MaxLengthValidator
from django.db import models

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law


class Collection(models.Model):
    user = models.ForeignKey(
        User,
        help_text='The user that owns the collection',
        related_name='collections',
        on_delete=models.CASCADE,
    )
    name = models.CharField(
        'a name for the collection',
        max_length=100,
    )
    notes = models.TextField(
        'notes about the collection',
        validators=[MaxLengthValidator(500)],
        max_length=500,
        blank=True,
    )
    created_date = models.DateTimeField(
        auto_now_add=True,
        help_text='Entry is created at this date time'
    )
    updated_date = models.DateTimeField(
        auto_now=True,
        help_text='Date time of last change'
    )
    private = models.BooleanField(
        default=True,
        help_text='If the collection should be only accessible by the owner'
    )

    def __str__(self):
        return self.name

    def __repr__(self):
        return '<Collection(#%s, %s, %s)>' % (self.pk, self.name, self.user)


class Favorite(models.Model):
    user = models.ForeignKey(
        User,
        help_text='The user that owns the favorite',
        related_name='favorites',
        on_delete=models.CASCADE,
    )
    collection = models.ForeignKey(
        Collection,
        help_text='The favorite belongs to this collection',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    name = models.CharField(
        'a name for the favorite',
        max_length=100,
    )
    notes = models.TextField(
        'notes about the favorite',
        validators=[MaxLengthValidator(500)],
        max_length=500,
        blank=True,
    )
    created_date = models.DateTimeField(
        auto_now_add=True,
        help_text='Entry is created at this date time'
    )
    updated_date = models.DateTimeField(
        auto_now=True,
        help_text='Date time of last change'
    )

    # For each content type a field
    case = models.ForeignKey(
        Case,
        help_text='The case that is favorited',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    law = models.ForeignKey(
        Law,
        help_text='The case that is favorited',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        unique_together = (
            ('case', 'collection', 'user'),
            ('law', 'collection', 'user'),
        )

    def __str__(self):
        return self.name

    def __repr__(self):
        return '<Favorite(#%s, %s, %s)>' % (self.pk, self.name, self.user)
