"""
Templatetags/filters for working with query strings

taken from https://djangosnippets.org/snippets/553/

version: 0.3
"""
from django import template
from django.http import QueryDict


class GetRequestQueryStringNode(template.Node):
    def __init__(self, asvar=None):
        self.asvar = asvar

    def __repr__(self):
        return '<GetRequestQueryStringNode>'

    def render(self, context):
        request = context.get('request', None)
        if request is None:
            return ''
        qstring = request.GET.urlencode()
        if self.asvar:
            context[self.asvar] = qstring
            return ''
        return qstring


def qstring(parser, token):
    """
    Get the current request's query string.

    USAGE: {% qstring %} or {% qstring as current_qstring %}
    """
    bits = token.split_contents()
    if len(bits) not in (1, 3):
        raise template.TemplateSyntaxError("'%s' takes zero or 2 arguments "
                                           "(as var_name)." % bits[0])
    if len(bits) == 1:
        asvar = None
    else:
        asvar = bits[2]
    return GetRequestQueryStringNode(asvar)


def _qdict_del_keys(qdict, del_qstring):
    for key in del_qstring.split('&'):
        try:
            del qdict[key]
        except KeyError:
            pass
    return qdict


def _qdict_set_keys(qdict, set_qstring):
    set_qdict = QueryDict(set_qstring)
    for key, values in set_qdict.items():
        qdict[key] = set_qdict[key]
    return qdict


def qstring_del(qstring, del_qstring):
    """
    Returns a query string w/o some keys, every value for each key gets deleted.

    More than one key can be specified using an & as separator:

    {{ my_qstring|qstring_del:"key1&key2" }}
    """
    qdict = QueryDict(qstring, mutable=True)
    return _qdict_del_keys(qdict, del_qstring).urlencode()


def qstring_set(qstring, set_qstring):
    """
    Updates a query string, old values get deleted.

    {{ my_qstring|qstring_set:"key1=1&key1=2&key2=3" }}
    """
    qdict = QueryDict(qstring, mutable=True)
    return _qdict_set_keys(qdict, set_qstring).urlencode()


register = template.Library()
register.tag(qstring)
register.filter('qstring_del', qstring_del)
register.filter('qstring_set', qstring_set)
