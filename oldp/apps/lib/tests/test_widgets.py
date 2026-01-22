"""Unit tests for the widgets module.

Tests cover:
- BootstrapDateRangeWidget
- CheckboxLinkWidget
- VisibleIfSetWidget
"""

import logging
from unittest.mock import MagicMock, patch

from django.db.models import BLANK_CHOICE_DASH
from django.http import QueryDict
from django.test import TestCase, tag

from oldp.apps.lib.widgets import (
    BootstrapDateRangeWidget,
    CheckboxLinkWidget,
    VisibleIfSetWidget,
)

logger = logging.getLogger(__name__)


@tag("lib", "widgets")
class BootstrapDateRangeWidgetTestCase(TestCase):
    """Tests for the BootstrapDateRangeWidget class."""

    def test_template_name(self):
        """Test that the widget uses the correct template."""
        widget = BootstrapDateRangeWidget()
        self.assertEqual(widget.template_name, "widgets/bootstrap_date_range.html")

    def test_inherits_from_date_range_widget(self):
        """Test that the widget inherits from DateRangeWidget."""
        from django_filters.widgets import DateRangeWidget

        widget = BootstrapDateRangeWidget()
        self.assertIsInstance(widget, DateRangeWidget)


@tag("lib", "widgets")
class CheckboxLinkWidgetTestCase(TestCase):
    """Tests for the CheckboxLinkWidget class."""

    def test_render_empty_value(self):
        """Test rendering with no value."""
        widget = CheckboxLinkWidget()
        widget.data = {}
        widget.choices = [("", "---------"), ("1", "Option 1"), ("2", "Option 2")]

        result = widget.render("test_field", None)

        self.assertIn("<ul", result)
        self.assertIn("</ul>", result)

    def test_render_with_value(self):
        """Test rendering with a selected value."""
        widget = CheckboxLinkWidget()
        widget.data = {}
        widget.choices = [("", "---------"), ("1", "Option 1"), ("2", "Option 2")]

        result = widget.render("test_field", "1")

        self.assertIn("<ul", result)
        self.assertIn("test_field", result)

    def test_render_option_blank_choice(self):
        """Test that blank choice is rendered as 'All'."""
        widget = CheckboxLinkWidget()
        widget.data = {}

        result = widget.render_option(
            "test_field", [], BLANK_CHOICE_DASH[0][0], BLANK_CHOICE_DASH[0][1]
        )

        self.assertIn("All", result)

    def test_render_option_with_dict_data(self):
        """Test rendering option with dict data."""
        widget = CheckboxLinkWidget()
        widget.data = {"other_field": "value"}

        result = widget.render_option("test_field", [], "1", "Option 1")

        self.assertIn("Option 1", result)
        self.assertIn("test_field=1", result)
        self.assertIn("href=", result)
        self.assertIn("checkbox", result)

    def test_render_option_selected(self):
        """Test rendering a selected option."""
        widget = CheckboxLinkWidget()
        widget.data = {"test_field": "1"}

        result = widget.render_option("test_field", ["1"], "1", "Option 1")

        self.assertIn("checked", result)
        self.assertIn('class="selected"', result)

    def test_render_option_not_selected(self):
        """Test rendering an unselected option."""
        widget = CheckboxLinkWidget()
        widget.data = {}

        result = widget.render_option("test_field", [], "1", "Option 1")

        self.assertNotIn("checked>", result)

    def test_option_string_selected(self):
        """Test option_string returns correct format for selected."""
        widget = CheckboxLinkWidget()
        result = widget.option_string(selected=True)

        self.assertIn("checked", result)
        self.assertIn("%(attrs)s", result)
        self.assertIn("%(query_string)s", result)

    def test_option_string_not_selected(self):
        """Test option_string returns correct format for unselected."""
        widget = CheckboxLinkWidget()
        result = widget.option_string(selected=False)

        self.assertNotIn("checked>", result)
        self.assertIn("checkbox", result)

    def test_render_with_query_dict_data(self):
        """Test rendering with QueryDict data."""
        widget = CheckboxLinkWidget()
        widget.data = QueryDict("other=value&page=1")
        widget.choices = [("1", "Option 1")]

        result = widget.render("test_field", "1")

        self.assertIn("<ul", result)

    def test_render_options_multiple_choices(self):
        """Test rendering options with multiple choices."""
        widget = CheckboxLinkWidget()
        widget.data = {}
        widget.choices = [
            ("", "---------"),
            ("a", "Alpha"),
            ("b", "Beta"),
            ("c", "Gamma"),
        ]

        result = widget.render("field", "a")

        self.assertIn("Alpha", result)
        self.assertIn("Beta", result)
        self.assertIn("Gamma", result)


@tag("lib", "widgets")
class VisibleIfSetWidgetTestCase(TestCase):
    """Tests for the VisibleIfSetWidget class."""

    def test_template_name(self):
        """Test that the widget uses the correct template."""
        mock_queryset = MagicMock()
        widget = VisibleIfSetWidget(queryset=mock_queryset)
        self.assertEqual(widget.template_name, "widgets/visible_if_set.html")

    def test_is_hidden_attribute(self):
        """Test that is_hidden is False."""
        mock_queryset = MagicMock()
        widget = VisibleIfSetWidget(queryset=mock_queryset)
        self.assertFalse(widget.is_hidden)

    def test_render_with_none_value(self):
        """Test rendering with None value."""
        mock_queryset = MagicMock()
        widget = VisibleIfSetWidget(queryset=mock_queryset)
        widget.data = {}

        with patch.object(widget, "get_context") as mock_get_context:
            mock_get_context.return_value = {"widget": {"value": None}}
            widget.render("test_field", None)
            mock_get_context.assert_called_once()

    def test_render_with_invalid_value(self):
        """Test rendering with invalid (non-integer) value."""
        mock_queryset = MagicMock()
        widget = VisibleIfSetWidget(queryset=mock_queryset)
        widget.data = {}

        with patch.object(widget, "get_context") as mock_get_context:
            mock_get_context.return_value = {"widget": {"value": None}}
            # Should handle ValueError gracefully
            widget.render("test_field", "not_an_int")
            # Value should be converted to None
            call_args = mock_get_context.call_args
            self.assertIsNone(call_args[0][1])  # second argument (value)

    def test_render_with_valid_integer_value(self):
        """Test rendering with valid integer value."""
        mock_obj = MagicMock()
        mock_obj.get_title.return_value = "Test Title"

        mock_queryset = MagicMock()
        mock_queryset.get.return_value = mock_obj

        widget = VisibleIfSetWidget(queryset=mock_queryset)
        widget.data = QueryDict("field=1")

        with patch.object(widget, "get_context") as mock_get_context:
            mock_get_context.return_value = {"widget": {"value": 1}}
            widget.render("field", "1")
            mock_get_context.assert_called_once()

    def test_get_context_with_valid_pk(self):
        """Test get_context retrieves object and updates context."""
        mock_obj = MagicMock()
        mock_obj.get_title.return_value = "Test Object Title"

        mock_queryset = MagicMock()
        mock_queryset.get.return_value = mock_obj

        widget = VisibleIfSetWidget(queryset=mock_queryset)
        widget.data = QueryDict("field=5&page=2", mutable=True)

        context = widget.get_context("field", 5, {})

        mock_queryset.get.assert_called_once_with(pk=5)
        self.assertIn("label", context)
        self.assertEqual(context["label"], "Test Object Title")
        self.assertIn("deselect_qstring", context)

    def test_get_context_removes_field_and_page_from_data(self):
        """Test that get_context removes the field and page from data."""
        mock_obj = MagicMock()
        mock_obj.get_title.return_value = "Title"

        mock_queryset = MagicMock()
        mock_queryset.get.return_value = mock_obj

        widget = VisibleIfSetWidget(queryset=mock_queryset)
        widget.data = QueryDict("field=5&page=2&other=value", mutable=True)

        context = widget.get_context("field", 5, {})

        # deselect_qstring should not contain 'field' or 'page'
        self.assertNotIn("field=", context["deselect_qstring"])
        self.assertNotIn("page=", context["deselect_qstring"])
        self.assertIn("other=value", context["deselect_qstring"])

    def test_get_context_with_nonexistent_pk(self):
        """Test get_context handles ObjectDoesNotExist gracefully."""
        from django.core.exceptions import ObjectDoesNotExist

        mock_queryset = MagicMock()
        mock_queryset.get.side_effect = ObjectDoesNotExist()

        widget = VisibleIfSetWidget(queryset=mock_queryset)
        widget.data = QueryDict("field=999")

        context = widget.get_context("field", 999, {})

        # Should not crash, and label should not be in context
        self.assertNotIn("label", context)

    def test_get_context_with_zero_value(self):
        """Test get_context with zero value doesn't query database."""
        mock_queryset = MagicMock()
        widget = VisibleIfSetWidget(queryset=mock_queryset)
        widget.data = {}

        widget.get_context("field", 0, {})

        # Should not query database for pk=0
        mock_queryset.get.assert_not_called()

    def test_get_context_with_negative_value(self):
        """Test get_context with negative value doesn't query database."""
        mock_queryset = MagicMock()
        widget = VisibleIfSetWidget(queryset=mock_queryset)
        widget.data = {}

        widget.get_context("field", -1, {})

        # Should not query database for negative pk
        mock_queryset.get.assert_not_called()

    def test_inherits_from_checkbox_link_widget(self):
        """Test that VisibleIfSetWidget inherits from CheckboxLinkWidget."""
        mock_queryset = MagicMock()
        widget = VisibleIfSetWidget(queryset=mock_queryset)
        self.assertIsInstance(widget, CheckboxLinkWidget)
