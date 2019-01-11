from django.db.models import BLANK_CHOICE_DASH
from django.forms.utils import flatatt
from django.utils.encoding import force_text
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _
from django_filters.widgets import LinkWidget


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
            'label': force_text(option_label)
        }

    def option_string(self, selected=False):
        if selected:
            return '<li><a%(attrs)s href="?%(query_string)s"><input type="checkbox" checked>  %(label)s</a></li>'
        else:
            return '<li><a%(attrs)s href="?%(query_string)s"><input type="checkbox">  %(label)s</a></li>'
