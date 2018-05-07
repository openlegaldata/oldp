from django.core.management import BaseCommand


class Command(BaseCommand):
    """

    Topic sources:
    - References: Law book

    """
    help = 'Assign topics to cases'

    def __init__(self):
        super(Command, self).__init__()

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20)
        parser.add_argument('--empty', action='store_true', default=False, help='Emptys existing index')

    def handle(self, *args, **options):
        pass