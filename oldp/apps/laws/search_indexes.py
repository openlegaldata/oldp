from django.utils.text import slugify
from haystack import indexes

from oldp.apps.laws.models import Law


class LawIndex(indexes.SearchIndex, indexes.Indexable):
    """

    # Define files that will be excluded in JSON export / Elasticsearch document
    es_fields_exclude = ['content', 'amtabk', 'footnotes', 'doknr']
    es_type = 'law'

    """
    FACET_MODEL_NAME = 'Law'

    text = indexes.CharField(document=True, use_template=True)
    slug = indexes.CharField(model_attr='slug')
    title = indexes.CharField()
    facet_model_name = indexes.CharField(faceted=True)
    book_code = indexes.CharField(faceted=True)

    # title_auto = indexes.EdgeNgramField()
    exact_matches = indexes.CharField()  # boost on exact match with this field

    def get_model(self):
        return Law

    def prepare_title(self, obj):
        return obj.get_title()

    def prepare_facet_model_name(self, obj):
        return self.FACET_MODEL_NAME

    def prepare_book_code(self, obj):
        return obj.book.code

    def prepare_exact_matches(self, obj):
        """All possible navigational queries"""
        sect = slugify(obj.section)
        code = obj.book.code.lower()

        return [
            code + ' ' + sect,
            sect + ' ' + code,
            # no whitespace
            code + sect,
            sect + code,
            obj.title
        ]

    def index_queryset(self, using=None):
        return self.get_model().objects.all().select_related('book').filter(book__latest=True)
