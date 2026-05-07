from django.utils import timezone
from refex.document import make_document
from refex.engines.regex import RegexLawExtractor
from refex.errors import RefExError
from refex.orchestrator import CitationExtractor

from oldp.apps.laws.models import Law, LawBook
from oldp.apps.laws.processing.processing_steps import LawProcessingStep
from oldp.apps.processing.errors import ProcessingError
from oldp.apps.references.models import LawReferenceMarker, ReferenceFromLaw
from oldp.apps.references.processing.processing_steps.extract_refs import (
    BaseExtractRefs,
)


class ProcessingStep(LawProcessingStep, BaseExtractRefs):
    """Processing step to extract law references."""

    description = "Extract references"
    marker_model = LawReferenceMarker
    reference_from_content_model = ReferenceFromLaw

    def __init__(self):
        super().__init__()

        self.law_engine = RegexLawExtractor()
        self.law_engine.law_book_codes = list(
            LawBook.objects.values_list("code", flat=True)
        )

        # Laws never cite cases, so the case engine is omitted entirely.
        self.extractor = CitationExtractor(engines=[self.law_engine])

    def process(self, law: Law) -> Law:
        """Extract law-to-law references from ``law.content``.

        The legacy extractor returned a rewritten content string with
        ``[ref=UUID]…[/ref]`` markers injected; refex 0.5.0 no longer
        injects markers into content, so ``law.content`` is no longer
        rewritten here.
        """
        try:
            self.law_engine.law_book_context = law.book.code

            doc = make_document(law.content, fmt="html")
            result = self.extractor.extract(doc)

            # Bulk-replace existing markers + their orphan References in
            # three SQL statements (skips the per-marker pre_delete
            # signal cascade); see ``BaseExtractRefs.bulk_delete_existing_markers``.
            self.bulk_delete_existing_markers(law)

            self.save_citations(doc, result.citations, law)

            # Stamp the run regardless of how many refs were found —
            # the absence of refs after a successful run is itself a
            # meaningful signal (vs. "extraction never ran").
            law.references_extracted_at = timezone.now()

            return law

        except RefExError as e:
            raise ProcessingError(e)
