import csv
import logging
import os

from django.conf import settings
from django.core.management import BaseCommand

from oldp.apps.references.models import ReferenceFromCase, ReferenceFromLaw

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Export reference data to CSV

    Output columns:
    from_id, to_id, from_title, to_title

    """
    help = 'Export reference data as CSV'

    def __init__(self):
        super(Command, self).__init__()

    def add_arguments(self, parser):

        parser.add_argument('output', type=str)

        parser.add_argument('--verbose', action='store_true', default=False)

        parser.add_argument('--override', action='store_true', default=False, help='Override existing output file')
        parser.add_argument('--append', action='store_true', default=False, help='Appends rows to existing output file')

        parser.add_argument('--limit', type=int, default=0)

    def handle_items(self, items, writer):
        """

        :param items: QuerySet
        :param writer: CSV writer
        :return:
        """
        for item in items:
            from_id = item.marker.referenced_by_id
            from_title = item.marker.referenced_by.get_title()

            if item.reference.law is not None:
                to_id = item.reference.law_id
                to_title = item.reference.law.get_title()

            elif item.reference.case is not None:
                to_id = item.reference.case_id
                to_title = item.reference.case.get_title()

            else:
                raise ValueError('law and case are both not NULL')

            logger.debug('From: %s; To: %s' % (from_title, to_title))

            writer.writerow([from_id, to_id, from_title, to_title])

    def handle(self, *args, **options):
        csv_path = os.path.join(settings.WORKING_DIR, options['output'])

        if os.path.exists(csv_path) and not options['override']:
            logger.error('Output file exist already: %s' % csv_path)
            return

        if options['append']:
            mode = 'a'
        else:
            mode = 'w'

        with open(csv_path, mode=mode) as csv_file:
            writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)

            logger.info('Writing to %s' % csv_path)

            # Case -> Law + Case
            from_case_items = ReferenceFromCase.objects.select_related(
                'reference__law', 'reference__law__book',
                'reference__case', 'reference__case__court',
                'marker', 'marker__referenced_by', 'marker__referenced_by__court') \
                .exclude(reference__law__isnull=True, reference__case__isnull=True)

            # Limit
            if options['limit'] > 0:
                from_case_items = from_case_items[:options['limit']]

            self.handle_items(from_case_items, writer)

            # Law -> Law + Case
            from_law_items = ReferenceFromLaw.objects.select_related(
                'reference__law', 'reference__law__book',
                'reference__case', 'reference__case__court',
                'marker', 'marker__referenced_by', 'marker__referenced_by__book', ) \
                .exclude(reference__law__isnull=True, reference__case__isnull=True)

            # Limit
            if options['limit'] > 0:
                from_law_items = from_law_items[:options['limit']]

            self.handle_items(from_law_items, writer)

            logger.info('Done')

