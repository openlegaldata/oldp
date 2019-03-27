import logging
import re

from django.conf import settings

from oldp.apps.courts.apps import CourtLocationLevel
from oldp.apps.courts.models import Court
from oldp.apps.courts.processing import CourtProcessingStep

logger = logging.getLogger(__name__)


class ProcessingStep(CourtProcessingStep):
    """Aliases should make it easier to find matching courts (e.g. Court.objects.get(aliases__contains=...))"""
    description = 'Set aliases for courts'

    def combine_type_location(self, types, location):
        """Combine type and location in both orders (AG Aachen + Aachen AG)"""
        for t in types:
            yield t + ' ' + location
            yield location + ' ' + t

    def process(self, court: Court) -> Court:
        """

        Generates all possible aliases for court names

        AG Aachen
        Aachen AG
        Aachener AG
        """

        aliases = [
            # Name is always as well an alias
            court.name
        ]

        if court.court_type is None:
            logger.warning('No court type: %s' % court)
            return court

        type_info = settings.COURT_TYPES.get_type(court.court_type)
        location_levels = type_info['levels']

        type_aliases = [
            court.court_type,
            type_info['name'],
        ]

        if CourtLocationLevel.CITY in location_levels:
            # Frankfurt (Oder)
            # ... an der Oder
            # Frankfurt am Main
            loc_name = court.city.name

            aliases.extend(self.combine_type_location(type_aliases, loc_name))

            for match in re.finditer(r'\s(a\.d\.|an der|am|im|unter|in der)\s(.*?)$', loc_name):
                # Frankfurt an der Oder -> Frankfurt (Oder)
                loc_name_x = '%s (%s)' % (loc_name[:match.start(0)], match.group(2))

                aliases.extend(self.combine_type_location(type_aliases, loc_name_x))

        if CourtLocationLevel.STATE in location_levels:
            # Add variations, e.g. Hamburg_er, Holstein_isches
            loc_name = court.state.name

            aliases.extend(self.combine_type_location(type_aliases, loc_name))

            for t in type_aliases:
                for v in ['es', 'er', 'isches']:
                    aliases.append(loc_name + v + ' ' + t)

        if CourtLocationLevel.COUNTRY in location_levels:
            # TODO Handle federal courts (BGH, ...)
            pass

        # Set as list
        court.aliases = Court.ALIAS_SEPARATOR.join(aliases)

        return court
