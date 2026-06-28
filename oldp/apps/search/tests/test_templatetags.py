"""Tests for the search templatetags — notably the env-configurable
homepage example queries (``search_example_queries``).
"""

from django.template import Context, Template
from django.test import SimpleTestCase, override_settings

from oldp.apps.search.templatetags.search import search_example_queries


class SearchExampleQueriesTagTest(SimpleTestCase):
    """``SEARCH_EXAMPLE_QUERIES`` (env ``DJANGO_SEARCH_EXAMPLE_QUERIES``) drives
    the homepage / no-results example search links.
    """

    @override_settings(SEARCH_EXAMPLE_QUERIES=["Maklervertrag", "Kündigungsschutzgesetz"])
    def test_returns_configured_queries(self):
        self.assertEqual(
            search_example_queries(), ["Maklervertrag", "Kündigungsschutzgesetz"]
        )

    @override_settings(SEARCH_EXAMPLE_QUERIES=[])
    def test_empty_returns_empty_list(self):
        self.assertEqual(search_example_queries(), [])

    @override_settings(SEARCH_EXAMPLE_QUERIES=['"Treu und Glauben"', "bgb 144"])
    def test_renders_as_search_links(self):
        # Each configured query becomes a /search/?q=… link (via search_url),
        # and there is no leftover boolean-OR example.
        tmpl = Template(
            "{% load search %}"
            "{% search_example_queries as ex %}"
            "{% for q in ex %}<a href='{{ q|search_url }}'>{{ q }}</a>{% endfor %}"
        )
        html = tmpl.render(Context({}))
        self.assertIn("/search/?q=", html)
        self.assertIn("Treu und Glauben", html)
        self.assertIn("bgb 144", html)
        self.assertNotIn(" OR ", html)
