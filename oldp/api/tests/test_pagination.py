from django.test import RequestFactory, TestCase, override_settings
from rest_framework.exceptions import NotFound

from oldp.api import (
    CappedLimitOffsetPagination,
    SmallResultsSetPagination,
    _reject_deep_offset,
)


@override_settings(PAGINATE_UNTIL=10, BULK_EXPORT_URL="https://example.test/dumps/")
class RejectDeepOffsetTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, **params):
        from rest_framework.request import Request

        return Request(self.factory.get("/api/cases/", params))

    def test_no_offset_is_allowed(self):
        _reject_deep_offset(self._request(), max_offset=10_000)

    def test_offset_at_limit_is_allowed(self):
        _reject_deep_offset(self._request(offset=10_000), max_offset=10_000)

    def test_offset_above_limit_raises(self):
        with self.assertRaises(NotFound) as ctx:
            _reject_deep_offset(self._request(offset=10_001), max_offset=10_000)
        self.assertIn("10001", str(ctx.exception))
        self.assertIn("10000", str(ctx.exception))
        self.assertIn("https://example.test/dumps/", str(ctx.exception))

    def test_non_integer_offset_is_ignored(self):
        _reject_deep_offset(self._request(offset="abc"), max_offset=10_000)


@override_settings(PAGINATE_UNTIL=10, BULK_EXPORT_URL="https://example.test/dumps/")
class SmallResultsSetPaginationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.paginator = SmallResultsSetPagination()

    def _request(self, **params):
        from rest_framework.request import Request

        return Request(self.factory.get("/api/cases/", params))

    def test_page_within_cap_allowed(self):
        self.paginator.paginate_queryset([1, 2, 3], self._request(page=1))

    def test_page_above_cap_raises(self):
        with self.assertRaises(NotFound) as ctx:
            self.paginator.paginate_queryset([], self._request(page=11))
        self.assertIn("Page 11", str(ctx.exception))
        self.assertIn("https://example.test/dumps/", str(ctx.exception))

    def test_deep_offset_rejected_even_on_page_pagination(self):
        with self.assertRaises(NotFound) as ctx:
            self.paginator.paginate_queryset(
                [], self._request(offset=999_999, limit=100)
            )
        self.assertIn("999999", str(ctx.exception))
        self.assertIn("https://example.test/dumps/", str(ctx.exception))

    def test_small_offset_ignored(self):
        # Offset within the 10 * max_page_size (=10,000) cap is accepted;
        # PageNumberPagination then ignores it and returns page 1.
        self.paginator.paginate_queryset(
            list(range(20)), self._request(offset=500, page=1)
        )

    def test_invalid_page_does_not_trip_cap_check(self):
        # Non-integer page must not raise our "exceeds maximum" NotFound;
        # DRF's own paginator then raises its own NotFound ("Invalid page").
        with self.assertRaises(NotFound) as ctx:
            self.paginator.paginate_queryset([1], self._request(page="abc"))
        self.assertNotIn("exceeds maximum", str(ctx.exception))


@override_settings(PAGINATE_UNTIL=10, BULK_EXPORT_URL="https://example.test/dumps/")
class CappedLimitOffsetPaginationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.paginator = CappedLimitOffsetPagination()

    def _request(self, **params):
        from rest_framework.request import Request

        return Request(self.factory.get("/api/cases/", params))

    def test_offset_within_cap_allowed(self):
        self.paginator.paginate_queryset(list(range(100)), self._request(offset=0))

    def test_offset_at_cap_allowed(self):
        # PAGINATE_UNTIL (10) * max_limit (1000) = 10,000
        self.paginator.paginate_queryset(list(range(20)), self._request(offset=10_000))

    def test_offset_above_cap_raises(self):
        with self.assertRaises(NotFound) as ctx:
            self.paginator.paginate_queryset(
                [], self._request(offset=19_362_600, limit=100)
            )
        self.assertIn("19362600", str(ctx.exception))
        self.assertIn("https://example.test/dumps/", str(ctx.exception))

    def test_limit_capped_at_max_limit(self):
        # DRF clamps limit to max_limit (1000); request survives cap check.
        self.paginator.paginate_queryset(
            list(range(100)), self._request(offset=0, limit=50_000)
        )

    def test_non_integer_offset_is_ignored(self):
        self.paginator.paginate_queryset(list(range(10)), self._request(offset="bogus"))
