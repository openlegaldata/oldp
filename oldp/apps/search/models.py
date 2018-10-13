# Create your models here.
from django.conf import settings
from django.db import models
from django.db.models import TextField, CharField, BooleanField, DateField, IntegerField, FloatField
from django.forms import model_to_dict
from elasticsearch_dsl import DocType, Text, String, Boolean, Date, Integer, Float

from oldp.apps.cases.search import CaseIndex


class RelatedContent(models.Model):
    seed_content = None
    related_content = None
    score = models.DecimalField(max_digits=12, decimal_places=8)

    class Meta:
        abstract = True

    def set_relation(self, seed_id, related_id):
        self.seed_content_id = seed_id
        self.related_content_id = related_id

    def set_score(self, score):
        self.score = score

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return 'RelatedContent(seed=%s, related=%s, score=%s)' % (self.seed_content, self.related_content, self.score)


def searchable_object_factory(o):
    assert isinstance(o, SearchableContent), 'Cannot run factory on non-searchable objects'

    class SearchableContentDocType(DocType):
        class Meta:
            doc_type = type(o).__name__.lower()
            index = settings.ELASTICSEARCH['index']

    # Add fields
    for field in o._meta.get_fields():
        # Django field types correspond to ES fields
        if isinstance(field, CharField):
            setattr(SearchableContentDocType, field.name, String())
        elif isinstance(field, TextField):
            setattr(SearchableContentDocType, field.name, Text())
        elif isinstance(field, BooleanField):
            setattr(SearchableContentDocType, field.name, Boolean())
        elif isinstance(field, DateField):
            setattr(SearchableContentDocType, field.name, Date())
        elif isinstance(field, IntegerField):
            setattr(SearchableContentDocType, field.name, Integer())
        elif isinstance(field, FloatField):
            setattr(SearchableContentDocType, field.name, Float())

    return SearchableContentDocType


class SearchableContent(object):
    """Abstract class for Elasticsearch content

    """
    es_type = None
    es_fields = None
    es_fields_exclude = []
    search_snippet = None
    search_score = 0.

    @staticmethod
    def from_hit(hit):
        """Constructs instance from ES hit object (JSON dict)

        :param hit: dict
        :return: SearchableContent
        """
        raise NotImplementedError('SearchableContent needs to implement from_hit()')

    def index(self):
        """Performs an index operation with content object (POST or PUT to ES)

        :return: index dict
        """

        # Convert django model to dict
        doc = model_to_dict(self, fields=self.es_fields, exclude=self.es_fields_exclude)

        # Set document id
        doc.update(meta={'id': self.get_id()})

        obj = searchable_object_factory(self)(**doc)

        return obj.save()  # Save in index


    def get_id(self):
        raise NotImplementedError()

    def get_title(self):
        raise NotImplementedError('SearchableContent needs to implement get_title()')

    def get_search_snippet(self):
        raise NotImplementedError('SearchableContent needs to implement get_snippet()')

    def set_search_snippet(self, snippet: str):
        """Sets search snippet (usually called with result from ES highlighting)

        :param snippet: str
        :return:
        """
        self.search_snippet = snippet

    def set_search_score(self, score):
        self.search_score = score

    def get_search_score(self):
        return self.search_score

    def pre_index(self, model_dict) -> dict:
        """ Signal before indexing

        This method is called before sending the object to ES. Use it to generate nested fields from foreign
        key relations.

        :param model_dict: dict created with model_to_dict method
        :return:
        """
        return model_dict

    def get_es_url(self):
        return None


class SearchQuery(models.Model):
    query = models.CharField(
        max_length=200,
        unique=True,
        help_text='Query as entered by user but all lower case'
    )
    counter = models.IntegerField(
        default=1,
        help_text='Count of query executions'
    )
    created_date = models.DateTimeField(
        auto_now_add=True,
        help_text='First query execution'
    )
    updated_date = models.DateTimeField(
        auto_now=True,
        help_text='Last query execution'
    )

    class Meta:
        indexes = [
            models.Index(fields=['query']),
        ]

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return 'SearchQuery(%s, %i, %s)' % (self.query, self.counter, self.updated_date)
