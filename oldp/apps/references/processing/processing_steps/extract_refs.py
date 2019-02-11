import logging
import os
from typing import Tuple, List

from refex.extractor import RefExtractor
from refex.models import RefType, Ref, RefMarker

from oldp.apps.cases.models import Case
from oldp.apps.laws.models import Law
from oldp.apps.processing.errors import ProcessingError
from oldp.apps.references.models import Reference
from oldp.apps.references.models import ReferenceMarker

logger = logging.getLogger(__name__)


class BaseExtractRefs(object):
    marker_model = None  # type: class[ReferenceMarker]
    reference_from_content_model = None  # type: class[ReferenceFromContent]

    def __init__(self):
        # RefExtractor must be initialized here to reset all settings
        self.extractor = RefExtractor()

    @staticmethod
    def get_law_books_from_file():
        """
        Read law book codes from file

        :return: List of law book codes
        """
        app_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        with open(os.path.join(app_dir, 'data', 'law_book_codes.txt')) as f:
            return [line.strip() for line in f.readlines()]

    def assign_law_ref(self, raw: Ref, ref: Reference) -> Reference:
        """
        Find corresponding database item to reference for laws
        """
        if raw.book is None or raw.section is None:
            raise ProcessingError('Reference data is not set')
        else:
            candidates = Law.objects.filter(book__slug=raw.book, slug=raw.section)

            if len(candidates) >= 1:
                # Multiple candidates should not occur
                ref.law = candidates.first()
            else:
                raise ProcessingError(
                    'Cannot find ref target in with book=%s; section=%s; for ref=%s' % (raw.book, raw.section, raw))

        return ref

    def assign_case_ref(self, raw: Ref, ref: Reference) -> Reference:
        """
        Find corresponding database item to reference for cases
        """

        candidates = Case.objects.filter(court__aliases__contains=raw.court, file_number=raw.file_number)

        if len(candidates) == 1:
            ref.case = candidates.first()
        elif len(candidates) > 1:
            # Multiple candidates
            # TODO better heuristic?
            ref.case = candidates.first()
        else:
            # Not found
            raise ProcessingError(
                'Cannot find ref target in with court=%s; file_number=%s; for ref=%s' % (
                    raw.court, raw.file_number, raw))

        return ref

    def save_markers(self, markers, referenced_by, assign_references=True) -> Tuple[List[ReferenceMarker], List[Reference]]:
        """Convert module objects into Django objects"""
        saved_markers = []
        saved_refs = []

        error_counter = 0
        success_counter = 0

        for marker in markers:  # type: RefMarker
            my_marker = self.marker_model(referenced_by=referenced_by, text=marker.text, start=marker.start, end=marker.end)
            my_marker.save()

            for ref in marker.references:  # type: Ref
                my_ref = Reference(to=marker.text)

                # Assign references to target items
                if assign_references:
                    try:
                        if ref.ref_type == RefType.LAW:
                            my_ref = self.assign_law_ref(ref, my_ref)
                        elif ref.ref_type == RefType.CASE:
                            my_ref = self.assign_case_ref(ref, my_ref)
                        else:
                            raise ProcessingError('Unsupported reference type: %s' % ref.ref_type)

                        success_counter += 1
                    except ProcessingError as e:
                        logger.error(e)
                        error_counter += 1

                # TODO Should we save references all the time or only on successful matching?
                my_ref.set_to_hash()
                my_ref.save()

                # Save in m2m helper
                self.reference_from_content_model(reference=my_ref, marker=my_marker).save()

                saved_refs.append(my_ref)
            saved_markers.append(my_marker)

        logger.debug('References: saved=%i; errors=%i' % (success_counter, error_counter))

        return saved_markers, saved_refs
