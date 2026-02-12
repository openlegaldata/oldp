"""Tests for review_status filtering in search API."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from oldp.apps.cases.models import Case
from oldp.apps.search.api import SearchViewMixin


class SearchViewMixinReviewStatusTestCase(TestCase):
    """Tests that SearchViewMixin.get_queryset() filters by review_status."""

    def test_get_queryset_filters_accepted_only(self):
        """SearchViewMixin applies review_status=accepted filter to SearchQuerySet."""
        mixin = SearchViewMixin()
        mixin.search_models = [Case]

        with patch("oldp.apps.search.api.SearchQuerySet") as mock_sqs_cls:
            mock_sqs = MagicMock()
            mock_sqs_cls.return_value = mock_sqs
            mock_sqs.models.return_value = mock_sqs
            mock_sqs.filter.return_value = mock_sqs

            result = mixin.get_queryset()

            mock_sqs.models.assert_called_once_with(Case)
            mock_sqs.filter.assert_called_once_with(review_status="accepted")
            self.assertEqual(result, mock_sqs)

    def test_get_queryset_without_models_still_filters(self):
        """SearchViewMixin applies review_status filter even without search_models."""
        mixin = SearchViewMixin()
        mixin.search_models = []

        with patch("oldp.apps.search.api.SearchQuerySet") as mock_sqs_cls:
            mock_sqs = MagicMock()
            mock_sqs_cls.return_value = mock_sqs
            mock_sqs.filter.return_value = mock_sqs

            result = mixin.get_queryset()

            mock_sqs.models.assert_not_called()
            mock_sqs.filter.assert_called_once_with(review_status="accepted")
            self.assertEqual(result, mock_sqs)
