import csv
import logging
import os
import re

from django.core.management import BaseCommand

from oldp.apps.cases.models import Case
from oldp.apps.courts.apps import CourtLocationLevel
from oldp.apps.courts.apps import CourtTypes
from oldp.apps.courts.models import Country, get_instance_or_create, State, City, Court

# Get an instance of a logger
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Processes law XML files (and adds them to database)'
    country = None

    def __init__(self):
        super(Command, self).__init__()

    def add_arguments(self, parser):
        # parser.add_argument('--output', type=str, default='http://localhost:9200')

        parser.add_argument('input', type=str)

        parser.add_argument('--limit', type=int, default=0)
        parser.add_argument('--max-lines', type=int, default=-1)

        parser.add_argument('--verbose', action='store_true', default=False)

        parser.add_argument('--override', action='store_true', default=False, help='Override existing index')
        parser.add_argument('--empty', action='store_true', default=False, help='Empty existing index')

    def empty(self):
        Case.objects.all().update(court_id=Court.DEFAULT_ID)
        Court.objects.exclude(pk=Court.DEFAULT_ID).delete()
        City.objects.all().delete()
        State.objects.exclude(pk=State.DEFAULT_ID).delete()

        # Add default court?
        default_state = State(pk=State.DEFAULT_ID, name='Unknown state', country=self.country)
        default_state.save()

        default_court = Court(pk=Court.DEFAULT_ID, name='Unknown court', code='unknown', state=default_state)
        default_court.save()

        # Add standard courts TODO more courts?
        Court(name='Europäischer Gerichtshof', code='EuGH', state=default_state).save()

    def handle(self, *args, **options):

        # if options['verbose']:
        #     root_logger.setLevel(logging.DEBUG)

        # Country identical for all courts
        self.country = get_instance_or_create(Country, 'Deutschland')

        # Delete all courts
        if options['empty']:
            self.empty()

        # Court types
        # type_mapping = CourtTypes.get_name_to_code_mapping()
        previous_state_name = None
        previous_state = None
        without_type_counter = 0
        court_counter = 0
        city_counter = 0
        state_counter = 0

        if not os.path.isfile(options['input']):
            logger.error('Cannot read from: %s' % options['input'])
            exit(1)

        logger.debug('Reading from: %s' % options['input'])

        with open(options['input']) as f:
            reader = csv.reader(f, delimiter='\t', quoting=csv.QUOTE_NONE)
            for row in reader:
                if len(row) != 3 or reader.line_num == 1 or row[1] == '':
                    continue

                if 0 < options['limit'] <= reader.line_num:
                    logger.debug('Limit reached')
                    break

                name = row[1].replace('_', '').strip()
                code = re.sub('[^0-9a-zA-Z]+', '', row[2])
                # code = row[2].replace(' ', '')

                # Fetch state
                state_name = row[0]
                if previous_state is not None and previous_state_name == state_name:
                    state = previous_state
                else:
                    try:
                        state = State.objects.get(name=state_name)

                    except State.DoesNotExist:
                        state = State(name=state_name, country=self.country)
                        state.save()
                        state_counter += 1

                # Fetch city and court type
                city = None
                court_type = Court.extract_type_code_from_name(name)

                if court_type is None:
                    logger.debug('Court type is none: %s' % row)
                    without_type_counter += 1
                else:
                    if CourtLocationLevel.CITY in CourtTypes().get_type(court_type)['levels']:
                        # Remove court type (left over is city name)
                        city_name = name.replace(court_type, '').strip()
                        city_name = city_name.replace(CourtTypes().get_type(court_type)['name'], '').strip()

                        try:
                            city = City.objects.get(name=city_name, state=state)
                        except City.DoesNotExist:
                            city = City(name=city_name, state=state)
                            city.save()
                            city_counter += 1

                # Save court
                # try:
                court = Court(name=name, code=code, state=state, city=city, court_type=court_type)
                court.save()
                court_counter += 1

                logger.debug('Saved court: %s' % court)

                # except IntegrityError as e:
                #     logger.error('Cannot save court: %s' % e)

                previous_state = state
                previous_state_name = state_name

        logger.info('Done. Courts: %i; Without types: %i; Cities: %i, States: %i' % (court_counter, without_type_counter,
                                                                                    city_counter, state_counter))

