import re

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils.text import slugify

from oldp.apps.cases.models import Case

ANNOTATION_VALUE_TYPE_STRING = 'str'
ANNOTATION_VALUE_TYPE_INTEGER = 'int'

color_re = re.compile('^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$')
validate_color = RegexValidator(color_re, 'Enter a valid color.', 'invalid')


class AnnotationLabel(models.Model):
    """
    Label for annotations (e.g. title, ...)
    """
    name = models.CharField(
        max_length=100,
        help_text='Verbose name, e.g. This Awesome annotation'
    )
    slug = models.SlugField(
        max_length=100,
        help_text='Identifier, e.g. this-awesome-annotation',
        db_index=True,
        blank=True,
    )
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE
        # TODO nullable? For global labels
    )
    trusted = models.BooleanField(
        help_text='Trusted annotations are display by default in front end',
        default=False,
        db_index=True,
    )
    private = models.BooleanField(
        help_text='Private annotations are only visible to its author',
        default=False,
        db_index=True,
    )
    many_annotations_per_label = models.BooleanField(
        help_text='A content object can have more than one annotation per label',
        default=False,
    )
    use_marker = models.BooleanField(
        default=False,
        help_text='Marker annotations are extracted from the text content and have a position in the text'
    )
    annotation_value_type = models.CharField(
        choices=(
            (ANNOTATION_VALUE_TYPE_STRING, 'String'),
            (ANNOTATION_VALUE_TYPE_INTEGER, 'Integer')
        ),
        default='str',
        max_length=5,
        help_text='Annotation values must be in this data type'
    )

    # belongs_to_type = models.CharField(
    #     choices=['case']
    # )
    color = models.CharField(
        # TODO Maybe color field? https://github.com/jaredly/django-colorfield/blob/master/colorfield/fields.py
        max_length=18,
        blank=True,
        null=True,
        validators=[validate_color],
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
        verbose_name = 'Label'
        db_table = 'annotations_label'
        unique_together = (
            ('slug', 'owner',)
        )

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.annotations = []


    def get_full_slug(self):
        return self.owner.username + '/' + self.slug

    def get_private(self):
        return self.private

    def get_owner(self):
        return self.owner

    def clean(self):
        if self.slug == '':
            self.slug = slugify(self.name)

        super().clean()

        if self.trusted and self.private:
            raise ValidationError({'trusted': 'Label cannot be `trusted` and `private` at the same time.'})

    def __repr__(self):
        return self.name

    def __str__(self):
        return '<Label(#%i, %s, %s)>' % (self.pk, self.slug, self.owner.username)


class Annotation(models.Model):
    belongs_to = None
    label = models.ForeignKey(
        AnnotationLabel,
        on_delete=models.CASCADE
    )
    value_str = models.CharField(
        max_length=250,
        null=True,
        blank=True,
    )
    value_int = models.IntegerField(
        null=True,
        blank=True,
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
        abstract = True
        #unique_together = ('label', 'belongs_to',)  # annotation per owner

    def value(self):
        if self.value_str is not None:
            return self.value_str
        elif self.value_int is not None:
            return self.value_int
        else:
            return None

    def get_private(self):
        return self.label.private

    def get_owner(self):
        return self.label.owner

    # def save(self, **kwargs):
    #     # self.clean()
    #     super().save(**kwargs)
    #
    # def get_queryset(self, request=None):
    #     qs = self.__class__._default_manager.select_related('belongs_to__court', 'label')
    #
    #     if self.request.user.is_authenticated:
    #         if self.request.user.is_staff:
    #             return qs.all()
    #         else:
    #             return qs.filter(Q(label__private=False) | Q(label__owner=self.request.user))
    #     else:
    #         return qs.filter(label__private=False)

    def clean(self):
        super().clean()

        # Check `many_to_annotations_per_label` constraint
        if not self.label.many_annotations_per_label and self.__class__._default_manager.filter(
            label=self.label,
            belongs_to=self.belongs_to
        ).exists():
            raise ValidationError({'label': 'Label does not allow multiple annotations for the same content object.'})

        # Check on values
        if self.label.annotation_value_type == ANNOTATION_VALUE_TYPE_STRING and self.value_str is None:
            raise ValidationError({
                'value_str': 'value_str cannot be null.',
            })
        if self.label.annotation_value_type == ANNOTATION_VALUE_TYPE_INTEGER and self.value_int is None:
            raise ValidationError({
                'value_int': 'value_int cannot be null.',
            })

    def __repr__(self):
        return self.label.slug + '=' + self.value()

    def __str__(self):
        return '<Annotation(#%i, %s, %s, %s)>' % (self.pk, self.label.slug, self.belongs_to, self.value())


class CaseAnnotation(Annotation):
    belongs_to = models.ForeignKey(
        Case,
        on_delete=models.CASCADE
    )

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
