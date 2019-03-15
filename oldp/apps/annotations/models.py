import re

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils.text import slugify

from oldp.apps.cases.models import Case
from oldp.apps.lib.markers import BaseMarker

ANNOTATION_VALUE_TYPE_STRING = 'str'
ANNOTATION_VALUE_TYPE_INTEGER = 'int'

color_re = re.compile('^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$')
validate_color = RegexValidator(color_re, 'Enter a valid color.', 'invalid')


class AnnotationLabel(models.Model):
    """
    Label for annotations (e.g. title, ...)
    """
    DEFAULT_COLOR = '#CCCCCC'

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
        default=DEFAULT_COLOR,
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
    """
    An annotation assigns a value (int or string) to a single content item, e.g. case.
    The meaning of the value is defined by the corresponding label.
    """
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

    def clean(self):
        super().clean()
        # Check `many_to_annotations_per_label` constraint
        if self.label.many_annotations_per_label is False:
            # Retrieve ids for a useful error message
            other_ids = list(self.__class__._default_manager\
                .filter(label=self.label, belongs_to=self.belongs_to)\
                .exclude(pk=self.pk)\
                .values_list('pk', flat=True))

            if len(other_ids) > 0:
                # TODO Returning the IDs as extra data field is currently not supoorted by DRF
                raise ValidationError({
                    'label': 'Label does not allow multiple annotations for the same content object. '
                             'Other annotation IDs: {}'.format(other_ids),
                })

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
        return self.label.slug + '=%s' % self.value()

    def __str__(self):
        return '<Annotation(#%i, %s, %s, %s)>' % (self.pk, self.label.slug, self.belongs_to, self.value())


class Marker(Annotation, BaseMarker):
    """
    Similar to an annotation, but linked to the textual content of an item, e.g. highlighted text or a citation.
    Start and end define the position of the value within the textual content.
    """

    start = models.PositiveIntegerField(
        db_index=True,
        default=0,
        help_text='Start position of marker (from 0)'
    )
    end = models.PositiveIntegerField(
        db_index=True,
        default=0,
        help_text='End position of marker',
    )

    def get_position(self):
        return self.start, self.end

    class Meta:
        abstract = True

    def get_start_position(self) -> int:
        return self.start

    def get_end_position(self) -> int:
        return self.end

    def get_marker_open(self) -> str:
        return '<span id="marker{}" class="marker marker-label{}" style="background-color: {}">'\
            .format(self.pk, self.label_id, self.label.color)

    def get_marker_close(self) -> str:
        return '<span class="marker-label">{}</span></span>'.format(self.label.name)

    def get_marker_close_format(self):
        # Do not use formatting
        pass

    def get_marker_open_format(self):
        pass

    def clean(self):
        super().clean()

        # Check for valid position: start <= end
        # - Markers with zero-length are allowed, hence, less or equal not only strict less.
        if self.start > self.end:
            raise ValidationError({
                'start': 'Invalid marker position. Start cannot be greater than end.'
            })

        # Check if marker overlaps with other markers
        other_ids = list(self.__class__._default_manager\
            .filter(Q(label=self.label),
                    Q(belongs_to=self.belongs_to),
                    Q(
                        Q(start__gte=self.start, start__lte=self.end) |  # Other start is in range
                        Q(end__gt=self.start, end__lt=self.end) |  # Other end is in range
                        Q(start__lte=self.start, end__gt=self.start) |  # Start is in range of others
                        Q(start__lte=self.end, end__gt=self.end)  # End is in range of others
                    )
                    )\
            .exclude(pk=self.pk)\
            .values_list('pk', flat=True))
        if len(other_ids) > 0:
            raise ValidationError({
                'start': 'Marker overlaps with other existing markers. Other marker IDs: %s' % other_ids,
            })

    def __str__(self):
        return '<Marker(#%i, %s, %s, %s)>' % (self.pk, self.label.slug, self.belongs_to, self.value())


# Content implementation (each content class should have its own implementation)
class CaseAnnotation(Annotation):
    belongs_to = models.ForeignKey(
        Case,
        on_delete=models.CASCADE
    )


class CaseMarker(Marker):
    belongs_to = models.ForeignKey(
        Case,
        on_delete=models.CASCADE
    )

