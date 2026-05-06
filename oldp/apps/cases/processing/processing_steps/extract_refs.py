import html
import logging
import re

from django.utils import timezone
from refex.errors import RefExError

from oldp.apps.cases.models import Case
from oldp.apps.cases.processing.processing_steps import CaseProcessingStep
from oldp.apps.processing.errors import ProcessingError
from oldp.apps.references.models import CaseReferenceMarker, ReferenceFromCase
from oldp.apps.references.processing.processing_steps.extract_refs import (
    BaseExtractRefs,
)

logger = logging.getLogger(__name__)


class ProcessingStep(CaseProcessingStep, BaseExtractRefs):
    description = "Extract references"
    # law_book_codes = None
    marker_model = CaseReferenceMarker
    reference_from_content_model = ReferenceFromCase

    def __init__(
        self, law_refs=True, case_refs=True, assign_refs=True, law_book_codes=None
    ):
        super().__init__()

        self.law_refs = law_refs
        self.case_refs = case_refs
        self.assign_refs = assign_refs

        self.extractor.do_case_refs = self.case_refs
        self.extractor.do_law_refs = self.law_refs
        # self.extractor.law_book_codes = list(LawBook.objects.values_list('code', flat=True))

        # When law_book_codes is None, leave the extractor's default in
        # place: legal-reference-extraction 0.5.0 ships ~1947 codes plus
        # unit hints in its bundled data file.
        if law_book_codes is not None:
            self.extractor.law_book_codes = law_book_codes

    def process(self, case: Case) -> Case:
        """Read case.content, search for references, add ref data (with start+end position) to case.

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

        logger.debug("Extract refs for %s" % case)

        try:
            # Clean HTML (should be done by scrapers)
            case.content = html.unescape(case.content)
            case.content = re.sub(r"</?verweis\.norm[^>]*>", "", case.content)
            case.content = re.sub(r"</?v\.abk[^>]*>", "", case.content)

            case.content = CaseReferenceMarker.remove_markers(
                case.content
            )  # TODO Removal only for legacy reasons

            # Do not change original content with markers
            _content, markers = self.extractor.extract(case.content)

            # Delete old markers
            CaseReferenceMarker.objects.filter(referenced_by=case).delete()

            marker_qs, ref_qs = self.save_markers(markers, case, self.assign_refs)

            # Stamp the run regardless of how many refs were found —
            # the absence of refs after a successful run is itself a
            # meaningful signal (vs. "extraction never ran").
            case.references_extracted_at = timezone.now()

            return case

        except RefExError as e:
            raise ProcessingError(e)
