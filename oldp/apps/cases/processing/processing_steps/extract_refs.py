import logging

from django.utils import timezone
from refex.document import make_document
from refex.engines.regex import RegexCaseExtractor, RegexLawExtractor
from refex.errors import RefExError
from refex.orchestrator import CitationExtractor

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
    marker_model = CaseReferenceMarker
    reference_from_content_model = ReferenceFromCase

    def __init__(
        self, law_refs=True, case_refs=True, assign_refs=True, law_book_codes=None
    ):
        super().__init__()

        self.law_refs = law_refs
        self.case_refs = case_refs
        self.assign_refs = assign_refs

        # Pattern: each engine is constructed once and held as a named
        # attribute so per-document context (court_context,
        # law_book_context) can be set in process() without isinstance
        # filtering on the orchestrator's engine list.
        self.law_engine = RegexLawExtractor() if law_refs else None
        if self.law_engine is not None and law_book_codes is not None:
            # When ``law_book_codes`` is None, leave the bundled list in
            # place: legal-reference-extraction 0.5.0 ships ~1947 codes
            # plus unit hints in its bundled data file.
            self.law_engine.law_book_codes = law_book_codes

        self.case_engine = RegexCaseExtractor() if case_refs else None

        engines = [e for e in (self.law_engine, self.case_engine) if e is not None]
        self.extractor = CitationExtractor(engines=engines)

    def process(self, case: Case) -> Case:
        """Extract references from ``case.content`` and persist marker + Reference rows.

        Strips legacy ``[ref=UUID]`` brackets from ``case.content`` first:
        those are stored artifacts from pre-2026 extraction runs that
        would otherwise corrupt the rendered case-detail view once new
        ``<a class="ref">`` markers are inserted on top of them. This is
        transitional cleanup that can be removed once the corpus has been
        re-extracted and confirmed clean.
        """
        if self.case_engine is not None:
            self.case_engine.court_context = case.court.code

        logger.debug("Extract refs for %s" % case)

        try:
            # Transitional: strip + persist legacy [ref=UUID]...[/ref] markers.
            # See class docstring above; remove once backfill is complete.
            case.content = CaseReferenceMarker.remove_markers(case.content)

            doc = make_document(case.content, fmt="html")
            result = self.extractor.extract(doc)

            CaseReferenceMarker.objects.filter(referenced_by=case).delete()

            self.save_citations(doc, result.citations, case, self.assign_refs)

            # Stamp the run regardless of how many refs were found —
            # the absence of refs after a successful run is itself a
            # meaningful signal (vs. "extraction never ran").
            case.references_extracted_at = timezone.now()

            return case

        except RefExError as e:
            raise ProcessingError(e)
