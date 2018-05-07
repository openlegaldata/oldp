"""

ES from bonsai/heroku:

https://bonsai.io/heroku/resources/elm-7226066

Requires existing index

curl -XPUT http://localhost:9200/oldp


"""
from datetime import datetime

from oldp.apps.cases.models import *
from oldp.apps.cases.processing.case_processor import CaseInputHandlerFS
from oldp.apps.laws.models import *


class OpenJurCaseInputHandlerFS(CaseInputHandlerFS):
    """Read cases for initial processing from file system"""

    def handle_input(self, input_content):
        try:
            logger.debug('Reading case JSON from %s' % input_content)

            tmp_case = json.loads(open(input_content).read())

            case = Case(
                title='',
                court_name=tmp_case['gericht'],
                date=datetime.strptime(tmp_case['datum'], '%d.%m.%Y').strftime('%Y-%m-%d'),
                file_number=tmp_case['aktenzeichen'],
                case_type=tmp_case['dokumenttyp'],
                source={
                    'name': tmp_case['fundstelle'],
                    'homepage': 'http://openjur.de',
                    'url': tmp_case['permalink']
                },
                pdf_url='openjur id to pdf',
                sections=self.get_sections_from_openjur(tmp_case)
            )

            self.pre_processed_content.append(case)

        except JSONDecodeError:
            raise ProcessingError('Cannot parse JSON from %s' % input_content)

    def get_sections_from_openjur(self, case):
        """

        Check for section titles

        T a t b e s t a n d
        Gründe:

        Extract headings + indents
        1.)
        IX.)
        (a)
        (aa)

        :param case: JSON case object from openJur API
        :return:
        """
        raw_content = case['entscheidung']
        sect_content = []
        raw_lines = str(raw_content).split('\n\n')
        for order, line in enumerate(raw_lines):
            sect_content.append(CaseContent(value=line, line=order+1, indent=0, order=order, heading=False))
        sections = [CaseSection('Entscheidung', content=sect_content)]

        return sections
