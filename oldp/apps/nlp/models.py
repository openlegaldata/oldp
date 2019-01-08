import pickle

from django.db import models

from oldp.apps.lib.markers import BaseMarker


class Entity(models.Model, BaseMarker):
    MONEY = "MONEY"
    EURO = "EURO"
    PERSON = "PERSON"
    LOCATION = "LOCATION"
    ORGANIZATION = "ORGANIZATION"
    PERCENT = "PERCENT"

    TYPES = (
        (MONEY, "Monetary values with currency."),
        (EURO, "Euro amounts."),
        (PERSON, "Name of a person or family."),
        (LOCATION, "Name of geographical or political locations."),
        (ORGANIZATION, "Any organizational entity."),
        (PERCENT, "Percentage amounts.")
    )
    type = models.CharField(
        help_text='Entity type',
        max_length=12,
        choices=TYPES,
        default=MONEY,  # TODO Should there be really a default?
        )
    # TODO Why can't this be a plain TextField? For numeric values we can add an extra field, that would allow as well aggregations directly in the DB.
    value = models.BinaryField(
        help_text='Content that represents the entity'
    )
    pos_start = models.IntegerField(
        help_text='Start position of entity in content',
        null=True
    )
    pos_end = models.IntegerField(
        null=True,
        help_text='End position of entity in content',
    )

    def get_start_position(self) -> int:
        return self.pos_start

    def get_end_position(self) -> int:
        return self.pos_end

    def get_marker_open_format(self) -> str:
        return '<span class="entity entity-{type}" id="entity{id}">'

    def get_marker_close_format(self) -> str:
        return '</span>'

    def __str__(self):
        return self.value

    def __repr__(self):
        return '<Entity({}: {}; {}-{})>'.format(self.type, pickle.loads(self.value), self.pos_start, self.pos_end)


class NLPContent(models.Model):
    nlp_entities = models.ManyToManyField(Entity, blank=True)

    class Meta:
        abstract = True
