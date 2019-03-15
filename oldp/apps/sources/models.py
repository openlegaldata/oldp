from django.core.validators import FileExtensionValidator
from django.db import models


class Source(models.Model):
    """
    Represents a source where we found content (i.e. a website, document corpus)
    """
    DEFAULT_ID = 1

    name = models.CharField(
        max_length=100,
        help_text='Name of source (crawler class)',
        db_index=True,
        unique=True,
    )
    homepage = models.URLField(
        max_length=200,
        help_text='Link to source homepage'
    )
    private = models.BooleanField(
        default=True,
        help_text='Private sources are not displayed in front-end'
    )

    def __repr__(self):
        return self.name

    def __str__(self):
        return '<Source(#%i, %s)>' % (self.pk, self.name)


class SourceContent(models.Model):
    """
    Content types that are assigned to sources inherit from this class
    """
    source = models.ForeignKey(
        Source,
        default=Source.DEFAULT_ID,
        on_delete=models.SET_DEFAULT,
    )
    source_url = models.URLField(
        max_length=255,
        help_text='Identifier of source object (URL for web pages, file names or IDs for corpora)'
    )

    source_file = models.FileField(  # TODO make this flexible
        help_text='Original source file (only PDF allowed)',
        upload_to='cases/',
        validators=[
            # Extensions should depend on source
            FileExtensionValidator(allowed_extensions=['pdf'])
        ],
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True

    def get_source_url(self) -> str:
        # deprecated
        return self.source_url
