import logging

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps import CaseProcessingStep
from oldp.apps.laws.models import LawBook
from oldp.apps.processing.processing_steps.extract_refs import BaseExtractRefs
from oldp.apps.references.models import CaseReferenceMarker

logger = logging.getLogger(__name__)


class ProcessingStep(CaseProcessingStep, BaseExtractRefs):
    description = 'Extract references'
    law_book_codes = None
    marker_model = CaseReferenceMarker

    def __init__(self, law_refs=True, case_refs=True):
        super().__init__()

        self.law_refs = law_refs
        self.case_refs = case_refs

        self.extractor.do_case_refs = self.case_refs
        self.extractor.do_law_refs = self.law_refs
        self.extractor.law_book_codes = list(LawBook.objects.values_list('code', flat=True))


    def process(self, case: Case) -> Case:
        """
        Read case.content, search for references, add ref marker (e.g. [ref=1]xy[/ref]) to text, add ref data to case.

        Ref data should contain position information, for CPA computations ...

        :param case: to be processed
        :return: processed case
        """

        self.extractor.court_context = case.court.code

        case.content, markers = self.extractor.extract(case.content)

        self.save_markers(markers, case)

        return case

