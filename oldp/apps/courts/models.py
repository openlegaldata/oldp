from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.text import slugify

from oldp.apps.courts.apps import CourtTypes
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
        max_length=100
    )
    code = models.CharField(
        max_length=2,
    )

    def __str__(self):
        return 'Country(name={})'.format(self.name)


class State(models.Model):
    DEFAULT_ID = 1

    name = models.CharField(
        max_length=50
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

    def __str__(self):
        return 'State(name={})'.format(self.name)


@receiver(pre_save, sender=State)
def pre_save_state(sender, instance: State, *args, **kwargs):

    if instance.slug is None or instance.slug == '':
        instance.slug = slugify(instance.name)


class City(models.Model):
    DEFAULT_ID = 1

    name = models.CharField(
        max_length=100,
        help_text='City name',
    )
    state = models.ForeignKey(
        State,
        on_delete=models.CASCADE,
        help_text='State of city'
    )

    def __str__(self):
        return 'City(name={})'.format(self.name)


class Court(models.Model):
    DEFAULT_ID = 1

    name = models.CharField(
        max_length=200,
        help_text='Full name of the court with location'
    )
    court_type = models.CharField(
        max_length=10,
        null=True,
        help_text='Court type AG,VG,...'
    )
    updated = models.DateTimeField(
        auto_now=True,
        help_text='Holds date time of last db update'
    )
    city = models.ForeignKey(
        City,
        on_delete=models.CASCADE,
        null=True,
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

    def is_default(self):
        return self.pk == self.DEFAULT_ID

    def get_id(self):
        return self.pk

    def get_url(self):
        return reverse('courts:detail', args=(self.slug,))

    def get_state(self):
        return State.objects.get(pk=self.state_id)

    def get_type_name(self):
        return self.court_type

    @staticmethod
    def extract_type_code_from_name(name):
        return find_from_mapping(name, CourtTypes().get_all_to_code_mapping())

    # def __repr__(self):
    #     return self.__str__()

    def __str__(self):
        return 'Court(name={}, code={})'.format(self.name, self.code)


@receiver(pre_save, sender=Court)
def pre_save_court(sender, instance: Court, *args, **kwargs):

    if instance.slug is None or instance.slug == '':
        if instance.court_type is not None and instance.city is not None:
            instance.slug = instance.court_type.lower() + '-' + slugify(instance.city.name)
        else:
            instance.slug = slugify(instance.code)

