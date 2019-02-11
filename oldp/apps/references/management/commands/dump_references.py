import csv
import logging
import os

from django.conf import settings
from django.core.management import BaseCommand
from django.core.paginator import Paginator

from oldp.apps.cases.models import Case
from oldp.apps.references.models import ReferenceFromCase, ReferenceFromLaw, ReferenceFromContent, Reference

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

    TODO Gephi output format
    - edges.csv: Source,Target
    - nodes.csv: Id,Label,[Attribute X]

    """
    help = 'Export reference data as CSV'
    chunk_size = 1000
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
        'to_law_title': lambda item: item.reference.law.title,
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
        parser.add_argument('--gephi', action='store_true', default=False, help='Use gephi output format (edges + nodes CSV)')

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

        # Use paginator to not load all rows at once in memory
        paginator = Paginator(items, self.chunk_size)
        for page in range(1, paginator.num_pages + 1):
            logger.debug('Page %i / %i' % (page, paginator.num_pages))

            for item in paginator.page(page).object_list:  # type: ReferenceFromContent
                row = {}
                for field in writer.fieldnames:  # Fieldnames are validated beforehand
                    try:
                        row[field] = self.available_fields[field](item)
                    except (AttributeError, KeyError):
                        # If field does not exist (e.g. from type is wrong), just return null
                        row[field] = None

                writer.writerow(rowdict=row)

    def handle_nodes_gephi(self, writer, limit=0, case_fields=[]):

        # Source
        # - case
        logger.info('Source case')

        qs = Case.objects \
            .filter(casereferencemarker__isnull=False) \
            .select_related('court', 'court__state') \
            .order_by('pk') \
            .values('id', 'slug', *case_fields) \
            .distinct()

        if limit > 0:
            qs = qs[:limit]

        # Use paginator to not load all rows at once in memory
        paginator = Paginator(qs, self.chunk_size)
        for page in range(1, paginator.num_pages + 1):
            logger.debug('Page %i / %i' % (page, paginator.num_pages))

            for item in paginator.page(page).object_list:  # type: dict
                row = {
                    'Id': 'case' + str(item['id']),
                    'Label': item['slug'],
                    'type': 'case',
                }

                for f in case_fields:
                    row[f] = item[f]

                writer.writerow(rowdict=row)

        # Targets
        # - law
        logger.info('Target nodes for law')

        qs = Reference.objects.select_related('law', 'law__book') \
            .order_by('law_id') \
            .filter(law__isnull=False) \
            .values('law_id', 'law__book__code', 'law__section') \
            .distinct()

        if limit > 0:
            qs = qs[:limit]

        # Use paginator to not load all rows at once in memory
        paginator = Paginator(qs, self.chunk_size)
        for page in range(1, paginator.num_pages + 1):
            logger.debug('Page %i / %i' % (page, paginator.num_pages))

            for item in paginator.page(page).object_list:  # type: dict
                row = {
                    'Id': 'law' + str(item['law_id']),
                    'Label': item['law__book__code'] + ' ' + item['law__section'],
                    'type': 'law',
                }

                writer.writerow(rowdict=row)

        # - case
        logger.info('Target nodes for case')

        qs = Reference.objects.select_related('case', 'case__court', 'case__court__state') \
            .order_by('case_id') \
            .filter(case__isnull=False) \
            .values('case_id', 'case__slug', *['case__' + f for f in case_fields]) \
            .distinct()

        if limit > 0:
            qs = qs[:limit]

        # Use paginator to not load all rows at once in memory
        paginator = Paginator(qs, self.chunk_size)
        for page in range(1, paginator.num_pages + 1):
            logger.debug('Page %i / %i' % (page, paginator.num_pages))

            for item in paginator.page(page).object_list:  # type: dict
                row = {
                    'Id': 'case' + str(item['case_id']),
                    'Label': item['case__slug'],
                    'type': 'case',
                }

                for f in case_fields:
                    row[f] = item['case__' + f]

                writer.writerow(rowdict=row)

    def handle_edges_gephi(self, model_cls, source_type, writer, limit=0):
        logger.info('Edges for %s' % source_type)

        # QuerySet
        qs = model_cls.objects \
                .select_related('reference', 'marker') \
                .exclude(reference__law__isnull=True, reference__case__isnull=True) \
                .values('marker__referenced_by_id', 'reference__case_id', 'reference__law_id')\
                .order_by('pk')

        if limit > 0:
            qs = qs[:limit]

        # Use paginator to not load all rows at once in memory
        paginator = Paginator(qs, self.chunk_size)
        for page in range(1, paginator.num_pages + 1):
            logger.debug('Page %i / %i' % (page, paginator.num_pages))

            for item in paginator.page(page).object_list:  # type: dict
                # Edge csv only contains source + target
                if item['reference__law_id'] is not None:
                    target = 'law%s' % item['reference__law_id']
                else:
                    target = 'case%s' % item['reference__case_id']

                writer.writerow(rowdict={
                    'Source': source_type + str(item['marker__referenced_by_id']),
                    'Target': target,
                })

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
        if opts['gephi']:
            fieldnames = ['Source', 'Target']
            logger.info('Using Gephie format')
        elif opts['fields'] == 'all':
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

            # Gephi
            if opts['gephi']:
                # Edges
                self.handle_edges_gephi(ReferenceFromCase, 'case', writer, opts['limit'])
                self.handle_edges_gephi(ReferenceFromLaw, 'law', writer, opts['limit'])

                # Nodes
                with open(csv_path + '.nodes.csv', mode) as nodes_csv_file:
                    case_fields = ['court__name', 'court__jurisdiction', 'court__level_of_appeal', 'court__state__name']
                    nodes_fields = ['Id', 'Label', 'type'] + case_fields

                    nodes_writer = csv.DictWriter(nodes_csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL,
                                        fieldnames=nodes_fields)

                    nodes_writer.writeheader()
                    self.handle_nodes_gephi(nodes_writer, opts['limit'], case_fields)

            else:
                # Case -> Law + Case
                from_case_items = ReferenceFromCase.objects.select_related(
                    'reference__law', 'reference__law__book',
                    'reference__case', 'reference__case__court',
                    'marker', 'marker__referenced_by', 'marker__referenced_by__court') \
                    .exclude(reference__law__isnull=True, reference__case__isnull=True) \
                    .order_by('pk')

                # Limit
                if opts['limit'] > 0:
                    from_case_items = from_case_items[:opts['limit']]

                self.handle_items(from_case_items, writer)

                # Law -> Law + Case
                from_law_items = ReferenceFromLaw.objects.select_related(
                    'reference__law', 'reference__law__book',
                    'reference__case', 'reference__case__court',
                    'marker', 'marker__referenced_by', 'marker__referenced_by__book', ) \
                    .exclude(reference__law__isnull=True, reference__case__isnull=True) \
                    .order_by('pk')

                # Limit
                if opts['limit'] > 0:
                    from_law_items = from_law_items[:opts['limit']]

                self.handle_items(from_law_items, writer)

            logger.info('Done')

