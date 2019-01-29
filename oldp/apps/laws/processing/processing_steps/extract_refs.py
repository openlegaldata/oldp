from refex.errors import RefExError

from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.processing.processing_steps import LawProcessingStep
from oldp.apps.processing.errors import ProcessingError
from oldp.apps.references.models import LawReferenceMarker, ReferenceFromLaw
from oldp.apps.references.processing.processing_steps.extract_refs import BaseExtractRefs


class ProcessingStep(LawProcessingStep, BaseExtractRefs):
    """
    Processing step to extract law references
    """
    description = 'Extract references'
    marker_model = LawReferenceMarker
    reference_from_content_model = ReferenceFromLaw

    def __init__(self):
        super().__init__()

        self.extractor.do_case_refs = False  # laws do not contain case refs
        self.extractor.do_law_refs = True
        self.extractor.law_book_codes = list(LawBook.objects.values_list('code', flat=True))

    def process(self, law: Law) -> Law:
        """
        Read law.content, search for references, add ref marker (e.g. [ref=1]xy[/ref]) to text, add ref data to law.

        Ref data should contain position information, for CPA computations ...

        :param law: to be processed
        :return: processed law
        """

        try:

            self.extractor.law_book_context = law.book.code

            law.content, markers = self.extractor.extract(law.content)

            LawReferenceMarker.objects.filter(referenced_by=law).delete()

            self.save_markers(markers, law)

            return law

        except RefExError as e:
            raise ProcessingError(e)
