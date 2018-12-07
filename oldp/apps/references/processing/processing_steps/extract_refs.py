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


class BaseExtractRefs():
    extractor = RefExtractor()
    marker_model = None  # type: class[ReferenceMarker]

    def get_law_books_from_file(self):
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
            try:
                ref.law = Law.objects.get(book__slug=raw.book, slug=raw.section)
            except Law.DoesNotExist:
                raise ProcessingError(
                    'Cannot find ref target in with book=%s; section=%s; for ref=%s' % (raw.book, raw.section, raw))

        # ref.to = json.dumps({
        #     'type': raw.ref_type,
        #     'book': raw.book,
        #     'section': raw.section,
        # })

        return ref

    def assign_case_ref(self, raw: Ref, ref: Reference) -> Reference:
        """
        Find corresponding database item to reference for cases
        """
        try:
            ref.case = Case.objects.get(court__aliases__contains=raw.court, file_number=raw.file_number)
        except Case.DoesNotExist:
            raise ProcessingError(
                'Cannot find ref target in with court=%s; file_number=%s; for ref=%s' % (
                raw.court, raw.file_number, raw))

        # ref.to = json.dumps({
        #     'type': raw.ref_type,
        #     'court': raw.court,
        #     'file_number': raw.file_number,
        # })
        return ref

    def save_markers(self, markers, referenced_by, assign_references=True) -> Tuple[List[ReferenceMarker], List[Reference]]:
        """Convert module objects into Django objects"""
        saved_markers = []
        saved_refs = []

        error_counter = 0
        success_counter = 0

        for marker in markers:  # type: RefMarker
            my_marker = self.marker_model(referenced_by=referenced_by, text=marker.text, uuid=marker.uuid, start=marker.start, end=marker.end)
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
                my_marker.references.add(my_ref)

                saved_refs.append(my_ref)
            saved_markers.append(my_marker)

        logger.debug('References: saved=%i; errors=%i' % (success_counter, error_counter))

        return saved_markers, saved_refs
