from django.core.exceptions import ObjectDoesNotExist
from django.db.models import BLANK_CHOICE_DASH
from django.forms.renderers import get_default_renderer
from django.forms.utils import flatatt
from django.utils.encoding import force_text
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _
from django_filters.widgets import LinkWidget, DateRangeWidget


class BootstrapDateRangeWidget(DateRangeWidget):
    """
    Simply use other template with Bootstrap style
    """
    template_name = 'widgets/bootstrap_date_range.html'


class CheckboxLinkWidget(LinkWidget):
    def render(self, name, value, attrs=None, choices=(), renderer=None):
        if not hasattr(self, 'data'):
            self.data = {}
        if value is None:
            value = ''
        final_attrs = self.build_attrs(self.attrs, extra_attrs=attrs)
        output = ['<ul%s>' % flatatt(final_attrs)]
        options = self.render_options(choices, [value], name)
        if options:
            output.append(options)
        output.append('</ul>')
        return mark_safe('\n'.join(output))

    def render_option(self, name, selected_choices,
                      option_value, option_label):
        option_value = force_text(option_value)
        if option_label == BLANK_CHOICE_DASH[0][1]:
            option_label = _("All")
        data = self.data.copy()
        data[name] = option_value
        selected = data == self.data or option_value in selected_choices
        try:
            url = data.urlencode()
        except AttributeError:
            url = urlencode(data)
        return self.option_string(selected) % {
            'attrs': selected and ' class="selected"' or '',
            'query_string': url,
            'name': name,
            'value': option_value,
            'label': force_text(option_label)
        }

    def option_string(self, selected=False):
        if selected:
            return '<li><a%(attrs)s href="?%(query_string)s"><input type="checkbox" name="%(name)s" value="%(value)s" checked>  %(label)s</a></li>'
        else:
            return '<li><a%(attrs)s href="?%(query_string)s"><input type="checkbox">  %(label)s</a></li>'


class VisibleIfSetWidget(CheckboxLinkWidget):
    """
    Checkbox link for referenced_by

    BUG: This only works with corresponding if-clause in form template
    """
    template_name = 'widgets/visible_if_set.html'
    is_hidden = False

    def __init__(self, queryset, attrs=None):
        super().__init__(attrs)

        self.queryset = queryset

    def render(self, name, value, attrs=None, choices=(), renderer=None):
        if not hasattr(self, 'data'):
            self.data = {}

        # Test if is a valid int
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = None

        if renderer is None:
            renderer = get_default_renderer()
        return mark_safe(renderer.render(self.template_name, self.get_context(name, value, attrs)))

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)

        if value is not None and value > 0:
            try:
                # Retrieve model from db
                obj = self.queryset.get(pk=value)

                # Update URL-params
                del self.data[name]
                if 'page' in self.data:
                    del self.data['page']

                context.update({
                    'label': obj.get_title(),
                    'deselect_qstring': self.data.urlencode(),
                })

            except ObjectDoesNotExist:
                # Do nothing (if label is not set, template does not print anything)
                pass

        return context

