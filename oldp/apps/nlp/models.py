from django.db import models


class Entity(models.Model):
    MONEY = "MONEY"
    TYPES = (
        (MONEY, "Monetary values with unit."),
    )
    type = models.CharField(max_length=12,
                            choices=TYPES,
                            default=MONEY
                            )
    value = models.CharField(
        max_length=100
    )
    pos_start = models.IntegerField(null=True)
    pos_end = models.IntegerField(null=True)


class NLPContent(models.Model):
    nlp_entities = models.ManyToManyField(Entity, blank=True)

    class Meta:
        abstract = True
