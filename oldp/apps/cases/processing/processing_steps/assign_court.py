import json
import logging
import re

from oldp.apps.backend.processing import ProcessingError
from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps import CaseProcessingStep
from oldp.apps.courts.apps import CourtTypes, CourtLocationLevel
from oldp.apps.courts.models import Court, City, State
from oldp.utils import find_from_mapping

logger = logging.getLogger(__name__)


class AssignCourt(CaseProcessingStep):
    description = 'Assign court to cases'
    # default_court = Court.objects.get(pk=Court.DEFAULT_ID)

    def __init__(self):
        super(AssignCourt, self).__init__()

    @staticmethod
    def find_court(query) -> Court:
        """

        Example court names:
        - Oberverwaltungsgericht für das Land Schleswig-Holstein
        - VG Magdeburg
        - {"name": "OVG L\u00fcneburg 5. Senat"}

        :param query: Dict(name, code)
        :return:
        """

        if 'code' in query:
            # Find based on code (EuGH, ...)
            try:
                return Court.objects.get(code=query['code'])
            except Court.DoesNotExist:
                pass

        if 'name' not in query:
            raise ProcessingError('Field name not in query')

        if ' ' not in query['name']:
            # Find based on name if name does not contain whitespaces
            try:
                return Court.objects.get(name=query['name'])
            except Court.DoesNotExist:
                pass

        # Determine type
        # print('Find court: %s' % query)
        court_type = Court.extract_type_code_from_name(query['name'])
        # print('Type code: %s' % court_type)

        if court_type is None:
            raise ProcessingError('Court type not found')

        location_levels = CourtTypes().get_type(court_type)['levels']

        # print('Location level: %s' % location_levels)

        # Look for states
        if CourtLocationLevel.STATE in location_levels:
            state_id_mapping = {}
            for r in State.objects.values_list('id', 'name'):
                if r[1] != '':
                    state_id_mapping[r[1]] = r[0]

                    # Add variations, e.g. Hamburg_er, Holstein_isches
                    for v in ['es', 'er', 'isches']:
                        state_id_mapping[r[1] + v] = r[0]

            state_id = find_from_mapping(query['name'], state_id_mapping)

            if state_id is not None:
                try:
                    logger.debug('Look for state=%i, type=%s' % (state_id, court_type))
                    return Court.objects.get(state_id=state_id, court_type=court_type)
                except Court.DoesNotExist:
                    pass

        # Look for cities
        if CourtLocationLevel.CITY in location_levels:
            city_id_mapping = {}
            for r in City.objects.values_list('id', 'name'):
                if r[1] != '':
                    city_id_mapping[r[1]] = r[0]

            city_id = find_from_mapping(query['name'], city_id_mapping)
            # print(city_id_mapping)
            if city_id is not None:
                try:
                    logger.debug('Look for city=%i, type=%s' % (city_id, court_type))
                    return Court.objects.get(city_id=city_id, court_type=court_type)
                except Court.DoesNotExist:
                    pass

        # Nothing found
        raise Court.DoesNotExist

        # if 'name' in query and 'code' in query:
        #     candidates = Court.objects.filter(Q(name=query['name']) | Q(code=query['code']))
        #     instance = candidates[0]
        #
        #     if len(candidates) == 0:
        #         raise Court.DoesNotExist
        # elif 'name' in query:
        #     instance = Court.objects.get(name=query['name'])
        #
        # else:
        #     raise ProcessingError('Court fields missing: %s' % query)

        return instance

    def process(self, case: Case) -> Case:

        court = json.loads(case.court_raw)

        if court['name'] == 'EU':
            court['code'] = 'EuGH'

        # Extract court chamber
        match = re.search(r' ([0-9]+)\. (Kammer|Senat)', court['name'])
        if match:
            court['name'] = court['name'][:match.start()] + court['name'][match.end():]
            case.court_chamber = match.group(0).strip()

        # Handle court instance
        # TODO Oberverwaltungsgericht für das Land Schleswig-Holsteins
        try:
            case.court = self.find_court(court)
            case.set_slug()

        except ProcessingError as e:
            logger.error('%s - %s' % (e, court))
        except Court.DoesNotExist:
            logger.warning('Count not assign court: %s' % court)

        return case
