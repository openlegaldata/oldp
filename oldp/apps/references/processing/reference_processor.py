from django.core.exceptions import ValidationError
from django.db import IntegrityError, DataError, OperationalError

from oldp.apps.cases.models import *
from oldp.apps.processing.content_processor import ContentProcessor, InputHandlerDB
from oldp.apps.processing.errors import ProcessingError
from oldp.apps.references.models import Reference

logger = logging.getLogger(__name__)


class ReferenceProcessor(ContentProcessor):
    model = Reference

    def __init__(self):
        super().__init__()

        self.db_models = [Reference]

    def empty_content(self):
        raise ProcessingError('Do not delete courts')

    def process_content(self):
        for content in self.pre_processed_content:  # type: Reference
            try:
                # First save (some processing steps require ids)
                content.full_clean()  # Validate model
                content.save()

                self.call_processing_steps(content)

                # Save again
                content.save()

                logger.debug('Completed: %s' % content)

                self.doc_counter += 1
                self.processed_content.append(content)

            except (ValidationError, DataError, OperationalError, IntegrityError, ProcessingError) as e:
                logger.error('Cannot process: %s; %s' % (content, e))
                self.processing_errors.append(e)
                self.doc_failed_counter += 1


class ReferenceInputHandlerDB(InputHandlerDB):
    def get_model(self):
        return Reference


if __name__ == '__main__':
    print('Do not call ReferenceProcessor directly. Run django command: ./manage.py process_courts')
