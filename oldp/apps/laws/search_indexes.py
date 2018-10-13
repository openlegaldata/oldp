from haystack import indexes

from oldp.apps.laws.models import Law


class LawIndex(indexes.SearchIndex, indexes.Indexable):
    text = indexes.CharField(document=True, use_template=True)
    slug = indexes.CharField(model_attr='slug')
    title = indexes.CharField(model_attr='title')

    def get_model(self):
        return Law

    def index_queryset(self, using=None):
        return self.get_model().objects.all()
