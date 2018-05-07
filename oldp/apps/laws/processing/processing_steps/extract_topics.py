"""

Topic from book title

- Gesetz (über|zum|zur) xxx
    - e.g. Gesetz über Europäische Betriebsräte
    - xx length < 30

- Ortsbewegliche-Druckgeräte-Verordnung
- Weinverordnung
- (Zweite|Dritte|...)Verordnung ((über das|die|das|den)|zur|zum|...)
- Raumordnungsgesetz
- Baugesetzbuch

"""

from oldp.apps.laws.models import Law
from oldp.apps.laws.processing.processing_steps import LawProcessingStep


class ExtractTopics(LawProcessingStep):
    def __init__(self):
        super(ExtractTopics, self).__init__()

    def process(self, law: Law) -> Law:

        # text, refs = self.extract_refs(law.text, law.book.code)
        # TODO LawBook processing step?

        return law
