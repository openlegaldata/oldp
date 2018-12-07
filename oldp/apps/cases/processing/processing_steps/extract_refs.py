import html
import logging
import re

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps import CaseProcessingStep
from oldp.apps.references.models import CaseReferenceMarker
from oldp.apps.references.processing.processing_steps.extract_refs import BaseExtractRefs

logger = logging.getLogger(__name__)


class ProcessingStep(CaseProcessingStep, BaseExtractRefs):
    description = 'Extract references'
    law_book_codes = None
    marker_model = CaseReferenceMarker

    def __init__(self, law_refs=True, case_refs=True, assign_refs=True):
        super().__init__()

        self.law_refs = law_refs
        self.case_refs = case_refs
        self.assign_refs = assign_refs

        self.extractor.do_case_refs = self.case_refs
        self.extractor.do_law_refs = self.law_refs
        # self.extractor.law_book_codes = list(LawBook.objects.values_list('code', flat=True))
        self.extractor.law_book_codes = self.get_law_books_from_file()


    def process(self, case: Case) -> Case:
        """
        Read case.content, search for references, add ref marker (e.g. [ref=1]xy[/ref]) to text, add ref data to case.

        Ref data should contain position information, for CPA computations ...

        :param case: to be processed
        :return: processed case
        """

        self.extractor.court_context = case.court.code

        """
        <verweis.norm>
        </verweis.norm>
        <v.abk ersatz="RDG"></v.abk>
        
        """

        # Clean HTML (should be done by scrapers)
        case.content = html.unescape(case.content)
        case.content = re.sub(r'</?verweis\.norm[^>]*>', '', case.content)
        case.content = re.sub(r'</?v\.abk[^>]*>', '', case.content)

        case.content, markers = self.extractor.extract(case.content)

        # Delete old markers
        CaseReferenceMarker.objects.filter(referenced_by=case).delete()

        marker_qs, ref_qs = self.save_markers(markers, case, self.assign_refs)

        return case

