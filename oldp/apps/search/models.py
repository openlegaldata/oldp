from django.db import models


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


class SearchableContent(object):
    """Abstract class for Elasticsearch content (using now haystack instead)

    """

    def get_title(self):
        raise NotImplementedError('SearchableContent needs to implement get_title()')

    def get_es_url(self):
        return None  # modelresult/cases.case.123


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
