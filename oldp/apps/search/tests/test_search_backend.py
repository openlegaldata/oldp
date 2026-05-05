"""Unit tests for the custom SearchBackend kwargs construction."""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from oldp.apps.search.search_backend import SearchBackend


def _make_backend():
    """Instantiate SearchBackend without connecting to ES."""
    with patch.object(SearchBackend, "__init__", return_value=None):
        b = SearchBackend.__new__(SearchBackend)
        SearchBackend.__init__(b)
    b.connections = MagicMock()
    b.RESERVED_WORDS = ()
    return b


class HighlightKwargsTest(SimpleTestCase):
    """Highlight kwargs must include max_analyzed_offset to avoid 400s on
    long doc fields (see incident 2026-05-05: case texts >1MB triggered
    search_phase_execution_exception in ES highlighter)."""

    def test_highlight_true_sets_max_analyzed_offset(self):
        backend = _make_backend()
        kwargs = backend.build_search_kwargs("test", highlight=True)
        self.assertIn("highlight", kwargs)
        self.assertEqual(kwargs["highlight"]["max_analyzed_offset"], 1_000_000)

    def test_highlight_false_omits_highlight_kwarg(self):
        backend = _make_backend()
        kwargs = backend.build_search_kwargs("test", highlight=False)
        self.assertNotIn("highlight", kwargs)

    def test_caller_overrides_can_replace_max_analyzed_offset(self):
        backend = _make_backend()
        kwargs = backend.build_search_kwargs(
            "test", highlight={"max_analyzed_offset": 500_000}
        )
        self.assertEqual(kwargs["highlight"]["max_analyzed_offset"], 500_000)

    def test_caller_overrides_preserve_max_analyzed_offset_when_not_set(self):
        backend = _make_backend()
        kwargs = backend.build_search_kwargs(
            "test", highlight={"fields": {"text": {"fragment_size": 200}}}
        )
        self.assertEqual(kwargs["highlight"]["max_analyzed_offset"], 1_000_000)
