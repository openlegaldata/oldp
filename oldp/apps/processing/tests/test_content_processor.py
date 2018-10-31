from django.test import TestCase

from oldp.apps.laws.models import LawBook
from oldp.apps.processing.content_processor import ContentProcessor


class ContentProcessorTestCase(TestCase):
    def test_load_processing_steps(self):
        cp = ContentProcessor()
        cp.model = LawBook

        steps = cp.get_available_processing_steps()
        self.assertEqual(1, len(steps), 'Invalid number of steps')
