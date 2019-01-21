import os
from json import JSONDecodeError

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, DataError, OperationalError

from oldp.apps.cases.models import *
from oldp.apps.processing.content_processor import ContentProcessor, InputHandlerFS, InputHandlerDB
from oldp.apps.processing.errors import ProcessingError
from oldp.apps.references.models import CaseReferenceMarker

logger = logging.getLogger(__name__)


class CaseProcessor(ContentProcessor):
    model = Case

    def __init__(self):
        super().__init__()

        self.es_type = 'case'
        self.db_models = [Case, CaseReferenceMarker]
        self.input_path = os.path.join(self.working_dir, 'cases')

    def empty_content(self):
        Case.objects.all().delete()

    def process_content_item(self, content: Case) -> Case:
        try:
            # First save (some processing steps require ids)
            # content.full_clean()  # Validate model
            content.save()

            self.call_processing_steps(content)

            # Save again
            content.save()

            logger.debug('Completed: %s' % content)

            self.doc_counter += 1
            self.processed_content.append(content)

        except (ValidationError, DataError, OperationalError, IntegrityError, ProcessingError) as e:
            logger.error('Cannot process case: %s; %s' % (content, e))
            self.processing_errors.append(e)
            self.doc_failed_counter += 1

        return content

    def process_content(self):
        if isinstance(self.input_handler, InputHandlerDB) and self.input_handler.input_limit > self.input_handler.per_page:
            # Use pagination if supported and no limit set
            logger.debug('Use pagination (per_page=%i)' % self.input_handler.per_page)

            paginator = Paginator(self.pre_processed_content, self.input_handler.per_page)
            for page in range(1, paginator.num_pages + 1):
                logger.debug('Page %i / %i' % (page, paginator.num_pages))

                for item in paginator.page(page).object_list:
                    self.process_content_item(item)

        else:
            for content in self.pre_processed_content:  # type: Case
                self.process_content_item(content)


class CaseInputHandlerDB(InputHandlerDB):
    def get_model(self):
        return Case


class CaseInputHandlerFS(InputHandlerFS):
    """Read cases for initial processing from file system"""
    dir_selector = '/*.json'

    def handle_input(self, input_content):
        try:
            logger.debug('Reading case JSON from %s' % input_content)

            case = Case.from_json_file(input_content)
            case.source_path = input_content

            self.pre_processed_content.append(case)

        except JSONDecodeError:
            raise ProcessingError('Cannot parse JSON from %s' % input_content)


if __name__ == '__main__':
    print('Do not call CaseProcessor directly. Run django command: ./manage.py process_cases')
