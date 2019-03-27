import json
import logging
import re

from django.conf import settings

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps import CaseProcessingStep
from oldp.apps.courts.apps import CourtLocationLevel
from oldp.apps.courts.models import Court, City, State
from oldp.apps.processing.errors import ProcessingError
from oldp.utils import find_from_mapping

logger = logging.getLogger(__name__)


class ProcessingStep(CaseProcessingStep):
    """

    Extract raw court names with this command:

    print('\n'.join([json.loads(s)['name'] for s in Case.objects.filter(court=1).values_list('court_raw', flat=True)[:10]]))

    """

    description = 'Assign court to cases'
    # default_court = Court.objects.get(pk=Court.DEFAULT_ID)

    def __init__(self):
        super().__init__()

    def remove_chamber(self, name):
        """
        Examples:

        LG Kiel Kammer für Handelssachen
        LG Koblenz 14. Zivilkammer
        OLG Koblenz 2. Senat für Bußgeldsachen
        Schleswig-Holsteinisches Oberlandesgericht Kartellsenat
        Vergabekammer Sachsen-Anhalt
        """

        chamber = None
        patterns = [
            '\s([0-9]+)(.*)$',
            '\s(Senat|Kammer) für(.*)$',
            '\s([a-zA-Z]+)(senat|kammer)(.*)$',
        ]

        for pattern in patterns:
            pattern = re.compile(pattern)

            match = re.search(pattern, name)
            if match:
                name = name[:match.start()] + name[match.end():]
                chamber = match.group(0).strip()

        return name.strip(), chamber

    def find_court(self, query) -> Court:
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

        name = query['name']

        if ' ' not in name:
            # Find based on name if name does not contain whitespaces
            try:
                return Court.objects.get(name=name)
            except Court.DoesNotExist:
                pass

        # Determine type
        # print('Find court: %s' % query)
        court_type = Court.extract_type_code_from_name(name)
        # print('Type code: %s' % court_type)

        if court_type is None:
            raise ProcessingError('Court type not found')

        location_levels = settings.COURT_TYPES.get_type(court_type)['levels']

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

            state_id = find_from_mapping(name, state_id_mapping)

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

            city_id = find_from_mapping(name, city_id_mapping)
            # print(city_id_mapping)
            if city_id is not None:
                try:
                    logger.debug('Look for city=%i, type=%s' % (city_id, court_type))
                    return Court.objects.get(city_id=city_id, court_type=court_type)
                except Court.DoesNotExist:
                    pass

        # Search by alias (use case-insensitive filter for umlauts)
        candidates = Court.objects.filter(aliases__icontains=name)
        if len(candidates) == 1:
            return candidates.first()
        elif len(candidates) > 1:
            # Multiple candidates found: fuzzy string matching?
            logger.warning('Multiple candidates found')

            # return candidates.first()

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


    def process(self, case: Case) -> Case:

        court = json.loads(case.court_raw)

        try:
            if 'name' not in court:
                raise ProcessingError('court_raw has no `name` field')

            if court['name'] == 'EU':
                court['code'] = 'EuGH'

            # Extract court chamber
            court['name'], case.court_chamber = self.remove_chamber(court['name'])

            # Handle court instance
            # TODO Oberverwaltungsgericht für das Land Schleswig-Holsteins

            case.court = self.find_court(court)
            case.set_slug()

        except ProcessingError as e:
            case.court_id = Court.DEFAULT_ID
            logger.error('Count not assign court: %s - %s' % (e, court))
        except Court.DoesNotExist:
            case.court_id = Court.DEFAULT_ID
            logger.warning('Count not assign court: %s' % court)

        return case
