from django.conf import settings
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk
from elasticsearch_dsl.connections import connections
from elasticsearch_dsl import DocType, Text, Date

connections.create_connection()


class CaseIndex(DocType):
    title = Text()
    _doc_type = 'xx'

    class Meta:
        doc_type = __name__.lower().replace('index', '')
        index = settings.ELASTICSEARCH['index']
    #     index =

    # def from_obj(self, obj):
    #     obj = CaseIndex(
    #         meta={'id': obj.id},
    #         author=self.author.username,
    #         posted_date=self.posted_date,
    #         title=self.title,
    #         text=self.text
    #     )
    #     obj.save()
    #     return obj.to_dict(include_meta=True)

def bulk_indexing():
    from oldp.apps.cases.models import Case

    CaseIndex.init()
    es = Elasticsearch()
    bulk(client=es, actions=(b.indexing() for b in Case.objects.all().iterator()))
