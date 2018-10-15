from haystack import indexes

from oldp.apps.cases.models import Case


class CaseIndex(indexes.SearchIndex, indexes.Indexable):
    text = indexes.CharField(document=True, use_template=True)
    # title = indexes.EdgeNgramField(use_template=True, template_name='search/indexes/cases/case_text.txt')

    private = indexes.BooleanField(model_attr='private')
    date = indexes.DateTimeField(model_attr='date')
    slug = indexes.CharField(model_attr='slug')
    title = indexes.EdgeNgramField() # model_attr='title')

    def get_model(self):
        return Case

    def index_queryset(self, using=None):
        return self.get_model().objects.all()
