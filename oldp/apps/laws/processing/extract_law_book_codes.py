import json
import os

from oldp.apps.backend.processing.law.law2es import LawProcessor

from oldp.apps.backend.processing import ContentProcessor


@DeprecationWarning
class LawBookCodeExtractor(ContentProcessor):
    """
    Helper class: Extract law book codes from XML files. Output is used for ref-extraction in case processing.
    """
    def __init__(self):
        super().__init__()

    def extract(self, output_path=None):
        if output_path is None:
            output_path = self.law_book_codes_path

        parser = LawProcessor()
        laws_dir = os.path.join(self.working_dir, 'gesetze-tools', 'laws')
        codes = {}

        for file_path in parser.find_all_law_files(laws_dir):
            book, docs = parser.parse_law_xml(file_path)

            if book is not None:
                codes[book['code']] = book['title']

        with open(output_path, 'w') as f:
            self.logger.debug('Writing output to %s' % output_path)
            json.dump(codes, f)
            f.close()

        return codes


if __name__ == '__main__':
    print(LawBookCodeExtractor().extract())
