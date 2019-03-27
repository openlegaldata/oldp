import logging
import re

from django.conf import settings

from oldp.apps.courts.models import Court
from oldp.apps.courts.processing import CourtProcessingStep

logger = logging.getLogger(__name__)


class ProcessingStep(CourtProcessingStep):
    description = 'Assign jurisdiction'

    def process(self, court: Court) -> Court:
        """
        Assign jurisdiction and level_of_appeal with regex on court name
        """

        # Test all types with regex
        for name in settings.COURT_JURISDICTIONS:
            if re.compile(settings.COURT_JURISDICTIONS[name], re.IGNORECASE).search(court.name):
                court.jurisdiction = name
                break

        # Test all types with regex
        for name in settings.COURT_LEVELS_OF_APPEAL:
            if re.compile(settings.COURT_LEVELS_OF_APPEAL[name], re.IGNORECASE).search(court.name):
                court.level_of_appeal = name
                break

        return court
