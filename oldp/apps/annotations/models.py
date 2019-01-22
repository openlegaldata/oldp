from django.contrib.auth.models import User
from django.db import models

from oldp.apps.cases.models import Case


class AnnotationLabel(models.Model):
    """

    Use cases:
    - title -> str
    - topics -> list[str]
        - order field
    - legigation value -> int

    """
    name = models.CharField(
        max_length=100,
        help_text='Verbose name, e.g. This Awesome annotation'
    )
    slug = models.SlugField(
        max_length=100,
        help_text='Identifier, e.g. this-awesome-annotation'
    )
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )
    trusted = models.BooleanField(
        help_text='Trusted annotations are display by default in front end',
        default=False,
    )
    private = models.BooleanField(
        help_text='Private annotations are only visible to its author',
        default=False,
    )
    # value_type = models.CharField(
    #     choices=['float', 'string', 'binary']
    # )
    # belongs_to_type = models.CharField(
    #     choices=['case']
    # )
    color = models.CharField(
        # TODO Maybe color field? https://github.com/jaredly/django-colorfield/blob/master/colorfield/fields.py
        max_length=18,
        blank=True,
        null=True,
    )
    use_marker = models.BooleanField(
        default=False,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Entry is created at this date time'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Date time of last change'
    )

    class Meta:
        db_table = 'labels'
        unique_together = (
            ('slug', 'owner',)
        )

    def __repr__(self):
        return 'Annotation: %s' % self.name

    def __str__(self):
        return '<AnnotaionLabel(#%i, %s)>' % (self.pk, self.name)


class Annotation(models.Model):
    belongs_to = None
    label = models.ForeignKey(
        AnnotationLabel,
        on_delete=models.CASCADE
    )
    value = models.TextField()
    # value_float = models.FloatField()
    # value_binary = models.BinaryField()  # maybe JSON field instead
    # order = models.PositiveIntegerField(
    #     default=0,
    #     help_text='',
    # )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Entry is created at this date time'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Date time of last change'
    )

    class Meta:
        abstract = True
        unique_together = ('label', 'belongs_to',)  # annotation per owner


class CaseAnnotation(Annotation):
    belongs_to = models.ForeignKey(
        Case,
        on_delete=models.CASCADE
    )


class AnnotationContent(object):
    def get_annotation_model(self):
        raise NotImplementedError()

    def get_annotations(self):
        return self.get_annotation_model().filter(belongs_to=self)

#
#
#
# class MarkerValue(AnnotationValue):
#     start_pos = models.IntField()
#     end_pos = models.IntField()
#
#     class Meta:
#         unique_together = ('annotation', 'belongs_to', 'start_pos', 'end_pos')  # more than one
#
