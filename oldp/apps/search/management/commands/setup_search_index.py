import logging

from django.core.management import BaseCommand

from oldp.apps.backend.processing.processing_steps.post.send_to_es import SendToES

# Get an instance of a logger
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Setup search index (currently Elasticsearch)'

    def __init__(self):
        super(Command, self).__init__()

    def add_arguments(self, parser):
        # parser.add_argument('--output', type=str, default='http://localhost:9200')
        pass

    def handle(self, *args, **options):
        SendToES().setup_index()
