import csv
import logging
import os

from django.conf import settings
from django.core.management import BaseCommand

from oldp.apps.references.models import ReferenceFromCase, ReferenceFromLaw, ReferenceFromContent

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Export reference data to CSV

    Output columns:

    from_id, to_id, from_title, to_title

    Full columns:

    - Ordinary from:
        from_id, from_type,
    - Case from:
        from_case_file_number, from_case_date, from_case_private, from_case_type, from_case_court_chamber,
        from_case_source_name
        - Case court from:
            from_case_court, from_case_court_name, from_case_court_city, from_case_court_state, from_case_court_jurisdiction,
            from_case_court_level_of_appeal
    - Law to:
        to_law_book_code
        to_law_section
    - Court to:
        to_case_court_name, to_case_court_jurisdiction, to_case_court_level_of_appeal

    """
    help = 'Export reference data as CSV'

    default_fields = ['from_id', 'from_type', 'from_case_file_number', 'to_id', 'to_type']

    available_fields = {
        'from_id': lambda item: item.marker.referenced_by_id,
        'from_type': lambda item: item.marker.referenced_by_type.__name__,
        'from_case_file_number': lambda item: item.marker.referenced_by.file_number,
        'from_case_date': lambda item: item.marker.referenced_by.date,
        'from_case_private': lambda item: int(item.marker.referenced_by.private),
        'from_case_type': lambda item: item.marker.referenced_by.type,
        'from_case_source_name': lambda item: item.marker.referenced_by.source_name,
        'from_case_court_chamber': lambda item: item.marker.referenced_by.court_chamber,

        'from_case_court_id': lambda item: item.marker.referenced_by.court.pk,
        'from_case_court_name': lambda item: item.marker.referenced_by.court.name,
        'from_case_court_city': lambda item: item.marker.referenced_by.court.city.name,
        'from_case_court_state': lambda item: item.marker.referenced_by.court.state.name,
        'from_case_court_jurisdiction': lambda item: item.marker.referenced_by.court.jurisdiction,
        'from_case_court_level_of_appeal': lambda item: item.marker.referenced_by.court.level_of_appeal,

        'to_id': lambda item: item.reference.law_id if item.reference.has_law_target() else item.reference.case_id,
        'to_type': lambda item: 'Law' if item.reference.has_law_target() else 'Case',

        'to_law_section': lambda item: item.reference.law.section,
        'to_law_book_code': lambda item: item.reference.law.book.code,
        'to_case_court_name': lambda item: item.reference.case.court.name,
        'to_case_court_jurisdiction': lambda item: item.reference.case.court.jurisidction,
        'to_case_court_level_of_appeal': lambda item: item.reference.case.court.level_of_appeal,

    }

    def __init__(self):
        super(Command, self).__init__()

    def add_arguments(self, parser):

        parser.add_argument('output', type=str, help='Path relative to working directory ({})'.format(settings.WORKING_DIR))
        parser.add_argument('--fields', type=str, default=','.join(self.default_fields),
                            help='Fields to be included in output. Separated by comma. Use "all" for all. Available: {}; Default: {}'.format(
                                ', '.join(self.available_fields.keys()),
                                ', '.join(self.default_fields)))

        parser.add_argument('--override', action='store_true', default=False, help='Override existing output file')
        parser.add_argument('--append', action='store_true', default=False, help='Appends rows to existing output file')

        parser.add_argument('--limit', type=int, default=0,
                            help='Max. number of references per content type (default: 0, 0=unlimited)')

    def handle_items(self, items, writer):
        """Build the actual CSV row

        :param items: QuerySet
        :param writer: CSV writer
        :return:
        """
        for item in items:  # type: ReferenceFromContent
            row = {}
            for field in writer.fieldnames:  # Fieldnames are validated beforehand
                try:
                    row[field] = self.available_fields[field](item)
                except (AttributeError, KeyError):
                    # If field does not exist (e.g. from type is wrong), just return null
                    row[field] = None

            writer.writerow(rowdict=row)

    def handle(self, *args, **opts):
        csv_path = os.path.join(settings.WORKING_DIR, opts['output'])

        if os.path.exists(csv_path) and not opts['override']:
            logger.error('Output file exist already: %s' % csv_path)
            return

        if opts['append']:
            mode = 'a'
        else:
            mode = 'w'

        # Field names
        if opts['fields'] == 'all':
            fieldnames = sorted(self.available_fields.keys())
        else:
            # Validate fields
            fieldnames = opts['fields'].split(',')
            for field in fieldnames:
                if field not in self.available_fields:
                    logger.error('Field is not part of available fields: %s' % field)
                    return

        with open(csv_path, mode=mode) as csv_file:
            writer = csv.DictWriter(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL,
                                    fieldnames=fieldnames)

            logger.info('Writing to %s' % csv_path)
            logger.debug('Fields: %s' % fieldnames)
            
            writer.writeheader()
            
            # Case -> Law + Case
            from_case_items = ReferenceFromCase.objects.select_related(
                'reference__law', 'reference__law__book',
                'reference__case', 'reference__case__court',
                'marker', 'marker__referenced_by', 'marker__referenced_by__court') \
                .exclude(reference__law__isnull=True, reference__case__isnull=True)

            # Limit
            if opts['limit'] > 0:
                from_case_items = from_case_items[:opts['limit']]

            self.handle_items(from_case_items, writer)

            # Law -> Law + Case
            from_law_items = ReferenceFromLaw.objects.select_related(
                'reference__law', 'reference__law__book',
                'reference__case', 'reference__case__court',
                'marker', 'marker__referenced_by', 'marker__referenced_by__book', ) \
                .exclude(reference__law__isnull=True, reference__case__isnull=True)

            # Limit
            if opts['limit'] > 0:
                from_law_items = from_law_items[:opts['limit']]

            self.handle_items(from_law_items, writer)

            logger.info('Done')

