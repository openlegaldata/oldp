"""

http://gg.docpatch.org/

http://gg.docpatch.org/grundgesetz-dev/out/brd_grundgesetz_59_2012-07-16.md

1. create law book (set icon=Art.
2. fetch version links from gg.docpatch
    a) download version md
    b) create law instance (extract refs)
    c) assign refs

TODO Alternative source:
    - Scrape from MD https://github.com/c3e/grundgesetz

"""
import logging

import pypandoc
import requests
from django.core.management import BaseCommand
from django.db import IntegrityError
from lxml import etree
from lxml.etree import tostring
from slugify import slugify

from oldp.apps.laws.models import LawBook, Law

logger = logging.getLogger(__name__)

# os.environ.setdefault('PYPANDOC_PANDOC', '/home/x/whatever/pandoc')


class Command(BaseCommand):
    help = 'Import law book "Grundgesetz"'

    def __init__(self):
        super(Command, self).__init__()

    def add_arguments(self, parser):
        # parser.add_argument('type', type=str, help='Content type (case, law, ...)')
        parser.add_argument('--limit', type=int, default=0)
        parser.add_argument('--empty', action='store_true', default=False, help='Delete existing revisions')
        pass

    def handle(self, *args, **options):

        # output = pypandoc.convert_text('#some title', 'docbook', format='html')
        # print(output)
        # exit(1)

        # Fetch meta information
        meta = requests.get(url='http://gg.docpatch.org/grundgesetz-dev/etc/meta.json').json()

        logger.info('Import GG: %s' % meta['covergage'])

        # Delete old GG
        if options['empty']:
            logger.debug('Deleting old law books (slug=gg only)')
            LawBook.objects.filter(slug='gg').delete()

        revs = list(reversed(list(meta['revisions'])))

        if options['limit'] > 0:
            revs = revs[:options['limit']]

        for key, rev in enumerate(revs):
            # brd_grundgesetz_59_2012-07-16.html
            book_url = 'http://gg.docpatch.org/grundgesetz-dev/out/brd_grundgesetz_%i_%s.db' % \
                       (len(meta['revisions']) - key - 1, rev['announced'])

            logger.debug('Downloading from: %s' % book_url)

            book_raw = requests.get(url=book_url).text.encode('utf-8')

            book = LawBook(code='Grundgesetz',
                           title='Grundgesetz für die Bundesrepublik Deutschland',
                           slug='gg',
                           revision_date=rev['announced'],
                           changelog='[{"type":"Stand", "text": "%s"}]' % rev['title'],
                           latest=key == 0)

            try:
                book.save()
            except IntegrityError as e:
                logger.error('Cannot save book: %s' % e)
                continue

            previous_law = None
            law_order = 1

            logger.debug('Law book saved: %s' % book)

            # Parse XML tree
            tree = etree.fromstring(book_raw)

            for sect in tree.xpath('sect1'):
                section_title = sect.xpath('title/text()')[0]
                logger.debug('Section: %s' % section_title)

                # if section_title == 'Grundgesetz für die Bundesrepublik Deutschland':
                #     continue

                book.add_section(from_order=law_order, title=section_title.strip())

                for law_key, law_raw in enumerate(sect.xpath('sect2')):
                    law_title = law_raw.xpath('title')[0]
                    law_title.getparent().remove(law_title)

                    # law_docbook = tostring(law_raw).decode('utf-8')
                    law_docbook = '\n'.join(tostring(x).decode('utf-8') for x in law_raw.iterchildren())
                    law_text = pypandoc.convert_text(law_docbook, 'html', format='docbook')
                    law_enbez = tostring(law_title, method="text").decode('utf-8').strip()

                    law = Law(book=book,
                              title='',
                              enbez=law_enbez,
                              slug=slugify(law_enbez),
                              content=law_text,
                              previous=previous_law,
                              order=law_order
                              )
                    law.save()
                    law_order += 1
                    previous_law = law

                    # TODO Save to ES
                    if law.book.latest:
                        pass

                    # print(law_raw)
                    # print(law_docbook)
                    # print(law_raw.html_content())
                    # break


            # Book sections
            # book.sections = {...}
            book.save()

            # break
