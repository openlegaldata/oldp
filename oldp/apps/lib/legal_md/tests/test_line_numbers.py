# TODO
import os
from unittest import TestCase

import markdown

RESOURCE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'resources')


class LineNumbersTest(TestCase):
    maxDiff = None
    extensions = [
            'oldp.apps.lib.legal_md.extensions.line_numbers',
        ]

    def assert_md_file(self, resource_name, msg=None):
        """Compare resource markdown file with corresponding html file"""
        with open(os.path.join(RESOURCE_DIR, resource_name + '.md')) as md_file:
            with open(os.path.join(RESOURCE_DIR, resource_name + '.html')) as html_file:
                md_content = md_file.read()
                expected = html_file.read()
                actual = markdown.markdown(md_content, extensions=self.extensions)

                self.assertEqual(expected, actual, msg)

    def test_single_line(self):
        self.assert_md_file('single_line')

    def test_mixed(self):
        self.assert_md_file('mixed')

    def test_case_text(self):
        self.assert_md_file('case_text')

    def test_lines_with_single_line_breaks(self):
        self.assert_md_file('lines_with_single_line_breaks')





