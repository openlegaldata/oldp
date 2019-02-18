from haystack import indexes

from oldp.apps.cases.models import Case


class CaseIndex(indexes.SearchIndex, indexes.Indexable):
    FACET_MODEL_NAME = 'Case'

    text = indexes.CharField(document=True, use_template=True)
    # title = indexes.CharField()
    # title = indexes.EdgeNgramField(use_template=True, template_name='search/indexes/cases/case_text.txt')

    private = indexes.BooleanField(model_attr='private')

    slug = indexes.CharField(model_attr='slug')

    facet_model_name = indexes.CharField(faceted=True)

    decision_type = indexes.CharField(faceted=True, null=True)
    court = indexes.CharField(faceted=True)
    court_jurisdiction = indexes.CharField(faceted=True, null=True)
    court_level_of_appeal = indexes.CharField(faceted=True, null=True)

    date = indexes.DateField(faceted=True)

    exact_matches = indexes.CharField()  # boost on exact match with this field

    # court_name_auto = indexes.EdgeNgramField(model_attr='court__name')

    def get_model(self):
        return Case

    # def prepare_title(self, obj):
    #     return obj.get_title()

    def prepare_facet_model_name(self, obj):
        return self.FACET_MODEL_NAME

    def prepare_decision_type(self, obj):
        return obj.type

    def prepare_court(self, obj):
        return obj.court.code  # TODO short name?

    def prepare_court_jurisdiction(self, obj):
        return obj.court.jurisdiction

    def prepare_court_level_of_appeal(self, obj):
        return obj.court.level_of_appeal

    def prepare_date(self, obj):
        return obj.date # .strftime('%Y-%m%-%d')

    def index_queryset(self, using=None):
        return Case.get_queryset().select_related('court', 'court__state')
