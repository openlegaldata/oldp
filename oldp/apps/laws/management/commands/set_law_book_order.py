import logging

from django.core.management import BaseCommand

from oldp.apps.laws.models import LawBook

LAW_BOOK_ORDER = {
    'bgb': 10,
    'agg': 9,
    'bafog': 9,

}

# Get an instance of a logger
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Assign predefined order values to law books based on slug'

    def __init__(self):
        super(Command, self).__init__()

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        order_mapping = LAW_BOOK_ORDER

        for book_slug in order_mapping:
            try:
                book = LawBook.objects.get(slug=book_slug)
                book.order = order_mapping[book_slug]
                book.save()

                logger.info('Updated %s' % book)
            except LawBook.DoesNotExist:
                logger.debug('Does not exist: %s' % book_slug)
                pass

        logger.info('done')
