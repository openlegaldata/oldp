import re

from django import template
from django.conf import settings

numeric_test = re.compile("^\d+$")
register = template.Library()


@register.filter('get_attribute')
def get_attribute(value, arg):
    """Gets an attribute of an object dynamically AND recursively from a string name"""
    if "." in str(arg):
        firstarg = str(arg).split(".")[0]
        value = get_attribute(value,firstarg)
        arg = ".".join(str(arg).split(".")[1:])
        return get_attribute(value,arg)
    if hasattr(value, str(arg)):
        return getattr(value, arg)
    elif hasattr(value, 'has_key') and value.has_key(arg):
        return value[arg]
    elif numeric_test.match(str(arg)) and len(value) > int(arg):
        return value[int(arg)]
    else:
        return settings.TEMPLATE_STRING_IF_INVALID
        # return 'no attr.' + str(arg) + 'for:' + str(value)


@register.simple_tag
def get_model_field(model, field_name, attr='verbose_name'):
    return getattr(model._meta.get_field(field_name), attr).title()
