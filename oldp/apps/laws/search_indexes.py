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
    title = indexes.EdgeNgramField(model_attr='title')

    def get_model(self):
        return Law

    def index_queryset(self, using=None):
        return self.get_model().objects.filter(book__latest=True)
