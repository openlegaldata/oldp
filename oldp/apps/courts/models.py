from django.conf import settings
from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.text import slugify

from oldp.utils import find_from_mapping


def get_instance_or_create(model: models.Model, name: str):
    try:
        inst = model.objects.get(name=name)

    except model.DoesNotExist:
        inst = model(name=name)
        inst.save()

    return inst


class Country(models.Model):
    DEFAULT_ID = 1

    name = models.CharField(
        max_length=100,
        db_index=True,
    )
    code = models.CharField(
        max_length=2,
        help_text='ISO country code (en, de, fr, ...)'
    )

    class Meta:
        ordering = ('name', )

    def __repr__(self):
        return '<Country(name={})>'.format(self.name)

    def __str__(self):
        return self.name


class State(models.Model):
    DEFAULT_ID = 1

    name = models.CharField(
        max_length=50,
        db_index=True,
    )
    country = models.ForeignKey(
        Country,
        on_delete=models.CASCADE
    )
    slug = models.SlugField(
        unique=True,
        max_length=50,
        help_text='Name field as slug'
    )

    class Meta:
        ordering = ('name', )

    def __str__(self):
        return self.name

    def __repr__(self):
        return '<State(name={})>'.format(self.name)


@receiver(pre_save, sender=State)
def pre_save_state(sender, instance: State, *args, **kwargs):

    if instance.slug is None or instance.slug == '':
        instance.slug = slugify(instance.name)


class City(models.Model):
    DEFAULT_ID = 1

    name = models.CharField(
        max_length=100,
        help_text='City name',
        db_index=True,
    )
    state = models.ForeignKey(
        State,
        on_delete=models.CASCADE,
        help_text='State of city'
    )

    class Meta:
        ordering = ('name', )

    def __str__(self):
        return self.name

    def __repr__(self):
        return '<City(name={})>'.format(self.name)


class Court(models.Model):
    DEFAULT_ID = 1
    ALIAS_SEPARATOR = '\n'

    name = models.CharField(
        max_length=200,
        help_text='Full name of the court with location',
        db_index=True,
    )
    aliases = models.TextField(
        null=True,
        blank=True,
        help_text='List of aliases (one per line)'
    )
    court_type = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        help_text='Court type AG,VG,...',
        db_index=True,
    )
    updated_date = models.DateTimeField(
        auto_now=True,
        help_text='Holds date time of last db update'
    )
    city = models.ForeignKey(
        City,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text='Court belongs to this city, if null court is state-level'
    )
    state = models.ForeignKey(
        State,
        on_delete=models.CASCADE,
        help_text='Court belongs to this state (derive country of this field)'
    )
    code = models.CharField(
        max_length=20,
        unique=True,
        help_text='Unique court identifier based on ECLI (e.g. BVerfG)'
    )
    slug = models.SlugField(
        unique=True,
        max_length=60,
        help_text='Type & city name as lowercase'
    )
    jurisdiction = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Jurisdiction of court (ordinary, civil, ...)',
        db_index=True,
    )
    level_of_appeal = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text='Subject-matter jurisdiction (local, federal, high court, ...)',
        db_index=True,
    )

    # Enriched content
    wikipedia_title = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text='Title of the corresponding Wikipedia article'
    )
    description = models.TextField(
        default='',
        blank=True
    )
    image = models.ImageField(
        upload_to='courts',
        null=True,
        blank=True
    )
    homepage = models.URLField(
        blank=True,
        null=True,
        help_text='Official court homepage'
    )
    street_address = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text='Street address with house number'
    )
    postal_code = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text='Postal code (ZIP code)'
    )
    address_locality = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text='Locality (city name)'
    )
    telephone = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text='Telephone number'
    )
    fax_number = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        help_text='Fax number'
    )
    email = models.EmailField(
        max_length=200,
        null=True,
        blank=True,
        help_text='Email address'
    )

    defer_fields_list_view = [
        'description',
        'homepage',
        'image',
        'street_address',
        'postal_code',
        'address_locality',
        'telephone',
        'fax_number',
        'email',
    ]

    class Meta:
        ordering = ('name', )
    
    def get_admin_url(self):
        return reverse('admin:courts_court_change', args=(self.pk, ))

    def is_default(self):
        return self.pk == self.DEFAULT_ID

    def get_id(self):
        return self.pk

    def get_absolute_url(self):
        return reverse('courts:detail', args=(self.slug,))

    def get_cases_list_url(self):
        return reverse('cases:index') + '?court={}'.format(self.pk)

    def get_type_name(self):
        return self.court_type

    @staticmethod
    def extract_type_code_from_name(name):
        return find_from_mapping(name, settings.COURT_TYPES.get_all_to_code_mapping())

    def __str__(self):
        return self.name

    def __repr__(self):
        return '<Court(name={}, code={})>'.format(self.name, self.code)


@receiver(pre_save, sender=Court)
def pre_save_court(sender, instance: Court, *args, **kwargs):

    if instance.slug is None or instance.slug == '':
        if instance.court_type is not None and instance.city is not None:
            instance.slug = instance.court_type.lower() + '-' + slugify(instance.city.name)
        else:
            instance.slug = slugify(instance.code)

