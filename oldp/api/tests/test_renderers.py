from datetime import date
from xml.etree import ElementTree

from django.test import SimpleTestCase, TestCase

from oldp.api.renderers import SafeXMLRenderer
from oldp.apps.cases.models import Case
from oldp.apps.courts.models import Court


class SafeXMLRendererTest(SimpleTestCase):
    def _render(self, data):
        return ElementTree.fromstring(SafeXMLRenderer().render(data))

    def test_strips_control_characters_from_text(self):
        root = self._render(
            {"title": "Urteil\x0bvom\x00 1. Mai", "items": ["a\x1fb", 3, None]}
        )

        self.assertEqual(root.findtext("title"), "Urteilvom 1. Mai")
        self.assertEqual([item.text for item in root.find("items")], ["ab", "3", None])

    def test_keeps_tab_newline_and_carriage_return(self):
        root = self._render({"content": "a\tb\nc\rd"})

        # XML parsers normalize a literal CR to LF.
        self.assertEqual(root.findtext("content"), "a\tb\nc\nd")

    def test_nested_containers_are_rendered(self):
        root = self._render({"court": {"name": "BGH", "aliases": ["X\x08", "Y"]}})

        self.assertEqual(root.findtext("court/name"), "BGH")
        self.assertEqual([item.text for item in root.find("court/aliases")], ["X", "Y"])


class CaseXMLFormatTest(TestCase):
    fixtures = [
        "locations/countries.json",
        "locations/states.json",
        "locations/cities.json",
        "courts/courts.json",
    ]

    def test_case_with_control_character_renders_as_xml(self):
        case = Case.objects.create(
            court=Court.objects.exclude(pk=Court.DEFAULT_ID).first(),
            file_number="XML-001",
            date=date(2021, 1, 1),
            content="<p>Tenor\x0bDie Klage wird abgewiesen.</p>",
            review_status="accepted",
        )

        response = self.client.get(f"/api/cases/{case.pk}/", {"format": "xml"})

        self.assertEqual(response.status_code, 200)
        root = ElementTree.fromstring(response.content)
        self.assertIn("TenorDie Klage wird abgewiesen.", root.findtext("content"))
