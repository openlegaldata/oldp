"""Unit tests for the LimitedPaginator class.

Tests cover:
- Limiting number of pages
- Edge cases with empty data
- Interaction with Django settings
"""

import logging

from django.test import TestCase, override_settings, tag

from oldp.utils.limited_paginator import LimitedPaginator

logger = logging.getLogger(__name__)


@tag("utils", "paginator")
@override_settings(PAGINATE_UNTIL=10)
class LimitedPaginatorTestCase(TestCase):
    """Tests for the LimitedPaginator class."""

    def test_num_pages_limited_to_setting(self):
        """Test that num_pages is limited to PAGINATE_UNTIL setting."""
        # Create data that would have 50 pages (500 items, 10 per page)
        items = list(range(500))
        paginator = LimitedPaginator(items, 10)

        # Should be limited to 10 pages (PAGINATE_UNTIL)
        self.assertEqual(paginator.num_pages, 10)

    def test_num_pages_not_limited_when_below_setting(self):
        """Test that num_pages is not limited when below PAGINATE_UNTIL."""
        # Create data that would have 5 pages (50 items, 10 per page)
        items = list(range(50))
        paginator = LimitedPaginator(items, 10)

        # Should be 5 pages (not limited)
        self.assertEqual(paginator.num_pages, 5)

    def test_num_pages_equal_to_setting(self):
        """Test num_pages when exactly equal to PAGINATE_UNTIL."""
        # Create data that would have exactly 10 pages
        items = list(range(100))
        paginator = LimitedPaginator(items, 10)

        self.assertEqual(paginator.num_pages, 10)

    def test_num_pages_with_empty_list(self):
        """Test num_pages with empty list and allow_empty_first_page=True."""
        items = []
        paginator = LimitedPaginator(items, 10, allow_empty_first_page=True)

        self.assertEqual(paginator.num_pages, 1)

    def test_num_pages_with_empty_list_no_empty_page(self):
        """Test num_pages with empty list and allow_empty_first_page=False."""
        items = []
        paginator = LimitedPaginator(items, 10, allow_empty_first_page=False)

        self.assertEqual(paginator.num_pages, 0)

    def test_num_pages_with_orphans(self):
        """Test num_pages calculation considers orphans."""
        # 95 items, 10 per page, 5 orphans = 9 pages (last 15 items on page 9)
        items = list(range(95))
        paginator = LimitedPaginator(items, 10, orphans=5)

        self.assertEqual(paginator.num_pages, 9)

    @override_settings(PAGINATE_UNTIL=5)
    def test_num_pages_with_lower_setting(self):
        """Test num_pages with different PAGINATE_UNTIL setting."""
        items = list(range(100))
        paginator = LimitedPaginator(items, 10)

        # Should be limited to 5 pages
        self.assertEqual(paginator.num_pages, 5)

    @override_settings(PAGINATE_UNTIL=100)
    def test_num_pages_with_higher_setting(self):
        """Test num_pages with higher PAGINATE_UNTIL setting."""
        items = list(range(500))
        paginator = LimitedPaginator(items, 10)

        # Should be limited to 50 pages (actual count)
        self.assertEqual(paginator.num_pages, 50)

    def test_count_property_unchanged(self):
        """Test that count property still works correctly."""
        items = list(range(500))
        paginator = LimitedPaginator(items, 10)

        # Count should reflect actual item count
        self.assertEqual(paginator.count, 500)

    def test_per_page_property(self):
        """Test that per_page property works correctly."""
        items = list(range(100))
        paginator = LimitedPaginator(items, 25)

        self.assertEqual(paginator.per_page, 25)

    def test_page_method_works(self):
        """Test that page() method returns correct page."""
        items = list(range(100))
        paginator = LimitedPaginator(items, 10)

        page = paginator.page(1)
        self.assertEqual(list(page.object_list), list(range(10)))

    def test_page_method_within_limit(self):
        """Test getting a page within the limit."""
        items = list(range(500))
        paginator = LimitedPaginator(items, 10)

        # Page 10 should be accessible (last allowed page)
        page = paginator.page(10)
        self.assertEqual(len(page.object_list), 10)

    def test_inherits_from_paginator(self):
        """Test that LimitedPaginator inherits from Django's Paginator."""
        from django.core.paginator import Paginator

        items = list(range(100))
        paginator = LimitedPaginator(items, 10)
        self.assertIsInstance(paginator, Paginator)

    def test_single_page_of_items(self):
        """Test with a single page of items."""
        items = list(range(5))
        paginator = LimitedPaginator(items, 10)

        self.assertEqual(paginator.num_pages, 1)

    def test_num_pages_cached(self):
        """Test that num_pages uses cached_property."""
        items = list(range(500))
        paginator = LimitedPaginator(items, 10)

        # Access twice - should be cached
        result1 = paginator.num_pages
        result2 = paginator.num_pages

        self.assertEqual(result1, result2)
        self.assertEqual(result1, 10)
