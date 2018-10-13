from haystack import indexes

from oldp.apps.cases.models import Case


class CaseIndex(indexes.SearchIndex, indexes.Indexable):
    text = indexes.CharField(document=True, use_template=True)
    private = indexes.BooleanField(model_attr='private')
    date = indexes.DateTimeField(model_attr='date')
    slug = indexes.CharField(model_attr='slug')
    title = indexes.CharField(model_attr='title')

    # text = indexes.CharField(document=True, use_template=True, template_name="search/book_text.txt")
    # title = indexes.CharField(model_attr='title')
    # authors = indexes.CharField()

    def get_model(self):
        return Case

    def index_queryset(self, using=None):
        return self.get_model().objects.all()
