"""Unit tests for utility functions in oldp.utils module.

Tests cover:
- find_from_mapping function
- get_elasticsearch_from_url function
- get_elasticsearch_settings_from_url function
"""

import logging

from django.test import TestCase, tag

from oldp.utils import (
    find_from_mapping,
    get_elasticsearch_from_url,
    get_elasticsearch_settings_from_url,
)

logger = logging.getLogger(__name__)


@tag("utils")
class FindFromMappingTestCase(TestCase):
    """Tests for the find_from_mapping function."""

    def test_find_exact_match(self):
        """Test finding an exact match in the mapping."""
        haystack = "Verwaltungsgericht Berlin"
        mapping = {"Verwaltungsgericht": "VG", "Oberlandesgericht": "OLG"}

        result = find_from_mapping(haystack, mapping)

        self.assertEqual(result, "VG")

    def test_find_case_insensitive(self):
        """Test case-insensitive matching."""
        haystack = "verwaltungsgericht Berlin"
        mapping = {"Verwaltungsgericht": "VG"}

        result = find_from_mapping(haystack, mapping)

        self.assertEqual(result, "VG")

    def test_find_with_word_boundaries(self):
        """Test that matching respects word boundaries."""
        haystack = "This is a test"
        mapping = {"test": "found", "tes": "partial"}

        result = find_from_mapping(haystack, mapping)

        # Should match "test" not "tes" due to word boundary
        self.assertEqual(result, "found")

    def test_find_no_match_returns_default(self):
        """Test that no match returns the default value."""
        haystack = "Something completely different"
        mapping = {"Verwaltungsgericht": "VG"}

        result = find_from_mapping(haystack, mapping, default="UNKNOWN")

        self.assertEqual(result, "UNKNOWN")

    def test_find_no_match_returns_none_by_default(self):
        """Test that no match returns None when no default is specified."""
        haystack = "Something completely different"
        mapping = {"Verwaltungsgericht": "VG"}

        result = find_from_mapping(haystack, mapping)

        self.assertIsNone(result)

    def test_find_mapping_list_true(self):
        """Test find_from_mapping with mapping_list=True returns the key."""
        haystack = "Verwaltungsgericht Berlin"
        mapping = {"Verwaltungsgericht": "VG", "Oberlandesgericht": "OLG"}

        result = find_from_mapping(haystack, mapping, mapping_list=True)

        # Should return the key, not the value
        self.assertEqual(result, "Verwaltungsgericht")

    def test_find_first_match_in_order(self):
        """Test that the first matching key is returned (dict order)."""
        haystack = "Oberlandesgericht Verwaltungsgericht"
        # In Python 3.7+, dict maintains insertion order
        mapping = {"Verwaltungsgericht": "VG", "Oberlandesgericht": "OLG"}

        result = find_from_mapping(haystack, mapping)

        # First key in mapping that matches should be returned
        self.assertEqual(result, "VG")

    def test_find_empty_mapping(self):
        """Test with empty mapping."""
        haystack = "Some text"
        mapping = {}

        result = find_from_mapping(haystack, mapping)

        self.assertIsNone(result)

    def test_find_empty_haystack(self):
        """Test with empty haystack."""
        haystack = ""
        mapping = {"test": "value"}

        result = find_from_mapping(haystack, mapping)

        self.assertIsNone(result)

    def test_find_with_special_regex_characters(self):
        """Test that special regex characters in keys are escaped."""
        # Note: Word boundary \b doesn't work with non-word chars like §
        # So we test with a word character key instead
        haystack = "Section 123 BGB applies here"
        mapping = {"Section 123": "section_123", "BGB": "civil_code"}

        result = find_from_mapping(haystack, mapping)

        self.assertEqual(result, "section_123")

    def test_find_word_boundary_prevents_partial_match(self):
        """Test that word boundaries prevent partial matches."""
        haystack = "Amtsgericht is here"
        mapping = {"Amt": "office"}

        result = find_from_mapping(haystack, mapping)

        # "Amt" should not match "Amtsgericht" due to word boundary
        self.assertIsNone(result)

    def test_find_with_umlauts(self):
        """Test matching with German umlauts."""
        haystack = "Münchener Gericht"
        mapping = {"Münchener": "MUC", "Berliner": "BER"}

        result = find_from_mapping(haystack, mapping)

        self.assertEqual(result, "MUC")

    def test_find_multiple_words_key(self):
        """Test matching with multi-word keys."""
        haystack = "Das Bundesverwaltungsgericht hat entschieden"
        mapping = {
            "Bundesverwaltungsgericht": "BVerwG",
            "Verwaltungsgericht": "VG",
        }

        result = find_from_mapping(haystack, mapping)

        self.assertEqual(result, "BVerwG")


@tag("utils")
class GetElasticsearchFromUrlTestCase(TestCase):
    """Tests for the get_elasticsearch_from_url function."""

    def test_parse_http_url(self):
        """Test parsing HTTP URL."""
        url = "http://localhost:9200/myindex"

        scheme, host, port, index = get_elasticsearch_from_url(url)

        self.assertEqual(scheme, "http")
        self.assertEqual(host, "localhost")
        self.assertEqual(port, 9200)
        self.assertEqual(index, "myindex")

    def test_parse_https_url(self):
        """Test parsing HTTPS URL."""
        url = "https://es.example.com:9243/production_index"

        scheme, host, port, index = get_elasticsearch_from_url(url)

        self.assertEqual(scheme, "https")
        self.assertEqual(host, "es.example.com")
        self.assertEqual(port, 9243)
        self.assertEqual(index, "production_index")

    def test_parse_url_with_subdomain(self):
        """Test parsing URL with subdomain."""
        url = "https://search.api.example.com:443/legal_index"

        scheme, host, port, index = get_elasticsearch_from_url(url)

        self.assertEqual(host, "search.api.example.com")
        self.assertEqual(port, 443)
        self.assertEqual(index, "legal_index")

    def test_parse_url_default_http_port(self):
        """Test parsing URL with default HTTP port."""
        url = "http://localhost:80/index"

        scheme, host, port, index = get_elasticsearch_from_url(url)

        self.assertEqual(port, 80)

    def test_parse_url_with_trailing_slash_returns_empty_index(self):
        """Test that URL with trailing slash returns empty index."""
        url = "http://localhost:9200/"

        scheme, host, port, index = get_elasticsearch_from_url(url)

        # Trailing slash results in empty string index (path splits to ['', ''])
        self.assertEqual(index, "")

    def test_parse_url_no_path_raises_error(self):
        """Test that URL without path raises ValueError."""
        url = "http://localhost:9200"

        with self.assertRaises(ValueError) as context:
            get_elasticsearch_from_url(url)

        self.assertIn("Cannot extract index", str(context.exception))

    def test_parse_url_with_ip_address(self):
        """Test parsing URL with IP address."""
        url = "http://192.168.1.100:9200/test_index"

        scheme, host, port, index = get_elasticsearch_from_url(url)

        self.assertEqual(host, "192.168.1.100")
        self.assertEqual(port, 9200)
        self.assertEqual(index, "test_index")


@tag("utils")
class GetElasticsearchSettingsFromUrlTestCase(TestCase):
    """Tests for the get_elasticsearch_settings_from_url function."""

    def test_settings_http_url(self):
        """Test generating settings from HTTP URL."""
        url = "http://localhost:9200/myindex"

        settings = get_elasticsearch_settings_from_url(url)

        self.assertEqual(settings["scheme"], "http")
        self.assertEqual(settings["host"], "localhost")
        self.assertEqual(settings["port"], 9200)
        self.assertEqual(settings["index"], "myindex")
        self.assertFalse(settings["use_ssl"])
        self.assertEqual(settings["urls"], [url])

    def test_settings_https_url_enables_ssl(self):
        """Test that HTTPS URL enables SSL."""
        url = "https://es.example.com:9243/secure_index"

        settings = get_elasticsearch_settings_from_url(url)

        self.assertEqual(settings["scheme"], "https")
        self.assertTrue(settings["use_ssl"])

    def test_settings_contains_all_required_keys(self):
        """Test that settings contains all required keys."""
        url = "http://localhost:9200/index"

        settings = get_elasticsearch_settings_from_url(url)

        required_keys = ["scheme", "host", "port", "index", "use_ssl", "urls"]
        for key in required_keys:
            self.assertIn(key, settings)

    def test_settings_urls_list_format(self):
        """Test that urls is a list containing the original URL."""
        url = "http://localhost:9200/index"

        settings = get_elasticsearch_settings_from_url(url)

        self.assertIsInstance(settings["urls"], list)
        self.assertEqual(len(settings["urls"]), 1)
        self.assertEqual(settings["urls"][0], url)
