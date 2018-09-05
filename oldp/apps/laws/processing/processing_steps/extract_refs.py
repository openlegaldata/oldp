import re

from oldp.apps.laws.models import Law
from oldp.apps.laws.processing.processing_steps import LawProcessingStep
from oldp.apps.references.models import LawReferenceMarker


class ExtractRefs(LawProcessingStep):
    """
    TODO We should define a `context` (law or case) for the extractor.
    """
    description = 'Extract references'

    def __init__(self):
        super(ExtractRefs, self).__init__()

    def process(self, law: Law) -> Law:

        content, refs = self.extract_refs(law, LawReferenceMarker.remove_markers(law.content), law.book.code)

        law.content = content
        law.reference_markers = refs

        return law

    def extract_refs(self, referenced_by: Law, text, book_code):
        """
        TODO

        § 343 der Zivilprozessordnung

        :param text:
        :param book_code:
        :return:
        """
        refs = []

        text = text.replace('&#167;', '§')
        search_text = str(text)

        def multi_sect(match):
            start = int(match.group(1))
            end = int(match.group(3)) + 1
            sects = []

            for sect in range(start, end):
                sects.append(sect)

            return sects

        def multi_book(match):
            start = int(match.group(1))
            end = int(match.group(3)) + 1
            return [book_code] * (end - start)

        patterns = [
            # §§ 664 bis 670
            {
                'pattern': '§§ ([0-9]+) (bis|und) ([0-9]+)',
                'book': multi_book,
                'sect': multi_sect
            },
            # Anlage 3
            {
                'pattern': 'Anlage ([0-9]+)',
                'book': lambda match: book_code,
                'sect': lambda match: 'anlage-%i' % int(match.group(1))
            },

            # § 1
            {
                'pattern': '§ ([0-9]+)(?:\s(Abs\.|Absatz)\s([0-9]+))?(?:\sSatz\s([0-9]+))?',
                'book': lambda match: book_code,
                'sect': lambda match: match.group(1)
            },


        ]

        for p in patterns:
            regex = p['pattern']

            res = re.finditer(regex, search_text)  # flags

            for ref_m in res:
                ref_text = ref_m.group(0)

                # Build ref with lambda functions
                ref_ids = []
                books = p['book'](ref_m)
                sects = p['sect'](ref_m)

                # Handle multiple ref ids in a single marker
                if not isinstance(books, str):
                    for key, book in enumerate(books):
                        ref_ids.append({
                            'book': book,
                            'sect': sects[key],
                            'type': 'law',
                        })

                else:
                    ref_ids.append({
                        'book': books,
                        'sect': sects,
                        'type': 'law'
                    })

                ref = LawReferenceMarker(referenced_by=referenced_by, text=ref_text, start=ref_m.start(), end=ref_m.end())
                ref.set_uuid()
                ref.set_references(ref_ids)
                refs.append(ref)

                # Remove from search text to avoid duplicate matches
                search_text = search_text[:ref_m.start()] + ('_' * (ref_m.end() - ref_m.start())) \
                              + search_text[ref_m.end():]
                # print('-------')

        # Sort by start and replace markers
        refs.sort(key=lambda r: r.start, reverse=False)
        marker_offset = 0
        for key, ref in enumerate(refs):
            text, marker_offset = ref.replace_content(text, marker_offset, key + 1)


        # print(search_text)
        #
        # text = text.replace(/Anlage ([0-9]+)/gim, '<a href="anlage-$1">Anlage $1</a>');
        #
        # // § 1 Absatz 3
        # // § 1 Abs. 1 Nr. 9 und 10
        # text = text.replace(/&#167; ([0-9]+) Abs. ([0-9]+) Nr. ([0-9]+) und ([0-9]+)/gim, '<a href="$1#$2.$3,$2.$4">&sect; $1 Abs. $2 Nr. $3 und $4</a>');
        #        text = text.replace(/&#167; ([0-9]+) Abs. ([0-9]+) Nr. ([0-9]+)/gim, '<a href="$1#$2.$3">&sect; $1 Abs. $2 Nr. $3</a>');
        #
        #               text = text.replace(/&#167; ([0-9]+) Abs. ([0-9]+)/gim, '<a href="$1#$2">&sect; $1 Abs. $2</a>');
        #                      text = text.replace(/&#167; ([0-9]+) Absatz ([0-9]+)/gim, '<a href="$1#$2">&sect; $1 Absatz $2</a>');
        #
        #
        #                             text = text.replace(/&#167; ([0-9]+) Nr. ([0-9]+)/gim, '<a href="$1#1.$2">&sect; $1 Nr. $2</a>');
        #
        #
        #                                    text = text.replace(/&#167;&#167; ([0-9]+) und ([0-9]+)/gim, '<a href="$1">&sect;&sect; $1</a> und <a href="$2">$2</a>');

        return text, refs
