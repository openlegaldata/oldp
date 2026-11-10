"""Tests for the Elasticsearch document templates (search/indexes/*)."""

from django.template.loader import render_to_string
from django.test import SimpleTestCase

from oldp.apps.laws.models import Law


class LawTextTemplateTests(SimpleTestCase):
    template = "search/indexes/laws/law_text.txt"

    def test_null_fields_render_empty_not_none(self):
        """Regression test: NULL ``amtabk``/``kurzue`` were indexed as "None".

        The literal text showed up in search snippets, e.g. the title line
        of BranntwMonG § 148 followed by two lines reading "None".
        """
        law = Law(
            title="Erwerb durch Privatpersonen",
            amtabk=None,
            kurzue=None,
            content="<p>(1) Erzeugnisse</p>",
        )
        text = render_to_string(self.template, {"object": law})
        self.assertNotIn("None", text)
        self.assertIn("Erwerb durch Privatpersonen", text)
        self.assertIn("Erzeugnisse", text)

    def test_set_fields_are_indexed(self):
        law = Law(
            title="Titel",
            amtabk="BranntwMonG",
            kurzue="Branntweinmonopolgesetz",
            content="<p>Text</p>",
        )
        text = render_to_string(self.template, {"object": law})
        self.assertIn("BranntwMonG", text)
        self.assertIn("Branntweinmonopolgesetz", text)
