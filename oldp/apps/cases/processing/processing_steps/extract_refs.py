import logging

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps import CaseProcessingStep
from oldp.apps.processing.errors import ProcessingError
from oldp.apps.references.models import CaseReferenceMarker, LawReference, CaseReference
from oldp.apps.references.refex.extractor import RefExtractor
from oldp.apps.references.refex.models import RefMarker, RefType

logger = logging.getLogger(__name__)


class ExtractRefs(CaseProcessingStep):
    description = 'Extract references'
    law_book_codes = None

    def __init__(self, law_refs=True, case_refs=True):
        super(ExtractRefs, self).__init__()

        self.law_refs = law_refs
        self.case_refs = case_refs

    def process(self, case: Case) -> Case:
        """
        Read case.content, search for references, add ref marker (e.g. [ref=1]xy[/ref]) to text, add ref data to case:

        case.refs {
            1: {
                section: ??,
                line: 1,
                word: 2,
                id: ecli://...,
            }
            2: {
                line: 2,
                word: 123,
                id: law://de/bgb/123
            }
        }

        Ref data should contain position information, for CPA computations ...

        :param case: to be processed
        :return: processed case
        """

        extractor = RefExtractor()
        extractor.court_context = case.court.code

        case.content, markers = extractor.extract(case.content)

        # Convert module objects into Django objects
        for marker in markers: # type: RefMarker
            my_marker = CaseReferenceMarker(referenced_by=case, text=marker.text)
            my_marker.save()

            for ref in marker.references:
                # TODO
                if ref.ref_type == RefType.LAW:
                    my_ref = LawReference()
                elif ref.ref_type == RefType.CASE:
                    my_ref = CaseReference()
                else:
                    raise ProcessingError('Unsupported reference type: %s' % ref.ref_type)

                my_ref.save()


        return case

