
# Get an instance of a logger
import logging

from django.core.management import BaseCommand

from oldp.apps.references.models import CaseReference, CaseReferenceMarker

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'For efficient debugging...'

    def __init__(self):
        super(Command, self).__init__()

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        r = {}
        # cc = CaseReference.objects.filter(marker__referenced_by__id=8).annotate(count=Count('to'))
        query = '''
          SELECT *, COUNT(*) as `count`
          FROM ''' + CaseReference._meta.db_table + ''' as r, ''' + CaseReferenceMarker._meta.db_table + ''' as m
          WHERE r.marker_id = m.id AND m.referenced_by_id = %(source_id)s
          GROUP BY `to_hash`
          ORDER BY `count` DESC'''
        params = {
            'source_id': 8,
        }
        cc = CaseReference.objects.raw(query, params)

        print(cc.query)
        # print(len(cc))
        for c in cc:
            print(c)
            print(c.get_target())
        #     if c.to in r:
        #         print(c.to)
        #     else:
        #         r[c.to] = c
        #
        # print(r)
