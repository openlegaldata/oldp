from django.db import models


class Entity(models.Model):
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
    type = models.CharField(max_length=12,
                            choices=TYPES,
                            default=MONEY
                            )
    value = models.BinaryField()
    pos_start = models.IntegerField(null=True)
    pos_end = models.IntegerField(null=True)


class NLPContent(models.Model):
    nlp_entities = models.ManyToManyField(Entity, blank=True)

    class Meta:
        abstract = True
