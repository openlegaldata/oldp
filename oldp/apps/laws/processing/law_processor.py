import os
import re

from django.db import DatabaseError
from lxml import etree
from slugify import slugify

from oldp.apps.laws.models import *
from oldp.apps.processing.content_processor import ContentProcessor, InputHandlerFS, InputHandlerDB
from oldp.apps.processing.errors import ProcessingError
from oldp.apps.references.models import LawReferenceMarker

logger = logging.getLogger(__name__)


class LawProcessor(ContentProcessor):
    model = Law

    def __init__(self):
        super().__init__()
        # self.law_book_codes_path = os.path.join(self.working_dir, 'law_book_codes.json')  # deprecated

        # self.db_models = [Law, LawBook, LawReferenceMarker]
        # self.es_type = 'law'
        # self.es_book_type = 'lawbook'

    def empty_content(self):
        logger.info('Deleting LawBook (without gg), Law, LawReferenceMarker objects')

        return LawBook.objects.exclude(slug='gg').delete(),\
               Law.objects.exclude(book__slug='gg').delete(),\
               LawReferenceMarker.objects.all().delete()

    def process_content(self):
        for i, content in enumerate(self.pre_processed_content):  # type: Law
            if i > 0:
                # .save() is already called by input handler
                content.previous = self.pre_processed_content[i - 1]

            if not isinstance(content, Law):
                raise ProcessingError('Invalid processing content: %s' % content)

            try:
                content.save()  # First save (steps require id)

                self.call_processing_steps(content)

                content.save()  # Save again

                self.doc_counter += 1
                self.processed_content.append(content)

            except ProcessingError as e:
                # logger.error('ERROR: ES - index already created? % s' % e)
                self.doc_failed_counter += 1
                logger.error(e)


class LawInputHandlerDB(InputHandlerDB):
    """Read laws for re-processing from db"""
    def get_model(self):
        return Law

    def get_queryset(self):
        return self.get_model().objects.exclude(book__slug='gg')


class LawInputHandlerFS(InputHandlerFS):
    """Read laws for initial processing from file system"""
    min_lines = None
    max_lines = None
    dir_selector = '/**/*.xml'

    def handle_input(self, input_content: str) -> None:
        """Parses law XML and creates book and law instances (append to processed_content)

        :param input_content: File path to law XML file
        :return:
        """

        logger.debug('Reading from %s' % input_content)

        # File exist?
        if not os.path.isfile(input_content):
            raise ProcessingError('Is not file: %s' % input_content)

        # Count lines
        num_lines = sum(1 for line in open(input_content))

        # Skip if lines count is invalid
        if (self.min_lines is not None and self.min_lines >= 0 and num_lines < self.min_lines) \
                or (self.max_lines is not None and 0 <= self.max_lines < num_lines):
            logger.info('Skip - File has invalid line count (%i): %s' % (num_lines, input_content))
            return

        # Parse XML tree
        tree = etree.parse(input_content)
        sort = 0
        docs = []

        # Prepare docs
        for idx, n in enumerate(tree.xpath('norm')):
            # Extract law content (with html tags)
            content = self.get_node_content(n, 'textdaten/text/Content/*')

            if idx == 0:
                # Save book with the first element
                book = self.handle_law_book(n)

            # Append section to book object if section title is found
            section_title = (n.xpath('metadaten/gliederungseinheit/gliederungstitel/text()') or [None])[0]
            if section_title is not None:
                book.add_section(from_order=sort, title=section_title.strip())

            # Create law object
            doc = Law(
                doknr=n.get('doknr'),
                section=(n.xpath('metadaten/enbez/text()') or [None])[0],
                amtabk=(n.xpath('metadaten/amtabk/text()') or [None])[0],
                kurzue=(n.xpath('metadaten/kurzue/text()') or [None])[0],
                title=(n.xpath('metadaten/titel/text()') or [''])[0].strip(),
                order=sort,  # use in frontend for sorting
                content=content,
                footnotes=json.dumps(self.get_node_content(n, 'textdaten/fussnoten/Content/*')),
                book=book,
            )

            # Perform processing steps
            # for processor in self.processing_steps:  # type: LawProcessingStep
            #     doc = processor.process(doc)

            # TODO is Verordnung? is Gesetz? strip <pre>?
            # slug (unique)
            slug = slugify(doc.section or '')

            if slug[:3] == 'ss-':  # Is section-symbol
                slug = slug[3:]

            doc.slug = slug

            if slug != '':
                logger.debug('Pre-processed: %s' % doc)
                docs.append(doc)
                sort += 1
            else:
                logger.warning('Ignore invalid document (no slug): %s' % doc)

        # Append to queue
        self.pre_processed_content.extend(docs)

    @staticmethod
    def get_node_content(node, xpath_str='textdaten/text/Content/*'):
        content = ''
        t = node.xpath(xpath_str)
        if len(t) > 0:
            for e in t:
                content += etree.tostring(e).decode('utf-8')
        return content

    def handle_law_book(self, node) -> LawBook:
        # alternative: amtabk, jurabk
        code_a = node.xpath('metadaten/amtabk/text()')

        if code_a:
            code = code_a[0]
        else:
            code_b = node.xpath('metadaten/jurabk/text()')

            if code_b:
                code = code_b[0]
            else:
                raise ProcessingError('Could not find book_code')


        revision_date_str = None
        revision_date = None
        changelog = []
        changelog_comments = node.xpath('metadaten/standangabe/standkommentar/text()')
        changelog_types = node.xpath('metadaten/standangabe/standtyp/text()')
        for key, value in enumerate(changelog_comments):
            changelog.append({
                'type': changelog_types[key],
                'text': value
            })

            if changelog_types[key] == 'Stand':
                revision_date_str = value

        if revision_date_str is not None:
            # print(revision_date_str)
            # [0-9]{2})\.([0-9]{4})
            match = re.search(r'(?P<day>[0-9]{1,2})\.(?P<month>[0-9]{1,2})\.(?P<year>[0-9]{4})', revision_date_str)
            if match:
                # Revision data as string (datetime.date is not JSON serializable)
                revision_date = datetime.date(int(match.group('year')), int(match.group('month')), int(match.group('day')))
                # revision_date = match.group('year') + '-' + match.group('month') + '-' + match.group('day')
                revision_date = revision_date.strftime('%Y-%m-%d')

        book_title_match = node.xpath('metadaten/langue/text()')

        if book_title_match:
            book_title = book_title_match[0].replace('\n', ' ')  # replace line breaks
        else:
            book_title = None

        book = LawBook(
            title=book_title,
            # gliederung=[],
            code=code,
            slug=slugify(code),
            footnotes=json.dumps(self.get_node_content(node, 'textdaten/fussnoten/Content/*')),  # On book level?
            changelog=json.dumps(changelog)
            # revision_date=revision_date
            # jurabk or amtabk missing?
        )

        if revision_date is not None:
            # TODO raise error if no revision date is provided?
            # raise ValueError('no revision date: %s; %s' % (changelog_comments, changelog_types))
            book.revision_date = revision_date

        try:
            book.save()
        except DatabaseError as e:
            # TODO set latest depending on revision - check first if other books exist?
            raise ProcessingError('Cannot save book: %s' % e)

        return book


if __name__ == '__main__':
    print('Do not call LawProcessor directly. Run django command: ./manage.py process_laws')
