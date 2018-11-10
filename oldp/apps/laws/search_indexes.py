from haystack import indexes

from oldp.apps.laws.models import Law


class LawIndex(indexes.SearchIndex, indexes.Indexable):
    """

    # Define files that will be excluded in JSON export / Elasticsearch document
    es_fields_exclude = ['content', 'amtabk', 'footnotes', 'doknr']
    es_type = 'law'

    """
    text = indexes.CharField(document=True, use_template=True)
    slug = indexes.CharField(model_attr='slug')
    title = indexes.CharField()
    facet_model_name = indexes.CharField(faceted=True)
    book_code = indexes.CharField(faceted=True)

    title_auto = indexes.EdgeNgramField()

    def get_model(self):
        return Law

    def prepare_title(self, obj):
        return obj.get_title()

    def prepare_facet_model_name(self, obj):
        return 'Law'

    def prepare_book_code(self, obj):
        return obj.book.code

    def index_queryset(self, using=None):
        return self.get_model().objects.filter(book__latest=True)
