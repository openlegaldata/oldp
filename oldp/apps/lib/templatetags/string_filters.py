import json

from django import template
from django.core.serializers import serialize
from django.db.models import QuerySet

register = template.Library()
# from django.template.defaulttags import register


@register.filter
def truncate_smart(value, limit=80, truncate='...'):
    """
    Truncates a string after a given number of chars keeping whole words.

    From: https://djangosnippets.org/snippets/1259/

    Usage:
        {{ string|truncate_smart }}
        {{ string|truncate_smart:50 }}
    """

    try:
        limit = int(limit)
    # invalid literal for int()
    except ValueError:
        # Fail silently.
        return value

    # Make sure it's unicode
    # value = unicode(value)

    # Return the string itself if length is smaller or equal to the limit
    if len(value) <= limit:
        return value

    # Cut the string
    value = value[:limit]

    # Break into words and remove the last
    words = value.split(' ')[:-1]

    # Join the words and return
    return ' '.join(words) + truncate


# Filter (used by templates)
@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def add_str(arg1, arg2):
    """concatenate arg1 & arg2"""
    return str(arg1) + str(arg2)


@register.filter
def jsonify(object):
    """Converts any object to JSON"""
    if isinstance(object, QuerySet):
        return serialize('json', object)
    return json.dumps(object)
