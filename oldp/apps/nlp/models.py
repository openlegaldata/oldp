from django.db import models


class NLPContent(models.Model):
    pass


class NLPContentReference(models.Model):
    """
    Content types should inherit from this abstract model to get access to NLPContent.
    """
    nlp_content = models.ForeignKey(NLPContent, null=True, default=None, on_delete=models.CASCADE)

    class Meta:
        abstract = True


class Entity(models.Model):
    nlp_content = models.ForeignKey(NLPContent, on_delete=models.CASCADE)
    type = models.CharField(
        max_length=100
    )
    value = models.CharField(
        max_length=100
    )
    pos_start = models.IntegerField(null=True)
    pos_end = models.IntegerField(null=True)
