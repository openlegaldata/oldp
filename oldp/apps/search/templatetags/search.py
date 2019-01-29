from datetime import datetime

from dateutil.relativedelta import relativedelta
from django import template
from django.template.defaultfilters import urlencode
from django.urls import reverse
from haystack.models import SearchResult
from haystack.utils.highlighting import Highlighter

register = template.Library()


@register.filter
def get_search_snippet(search_result: SearchResult, query: str) -> str:
    hlr = Highlighter(query, html_tag='strong')

    if search_result and hasattr(search_result, 'get_stored_fields') and 'text' in search_result.get_stored_fields():
        text = search_result.get_stored_fields()['text']

        return hlr.highlight(text)
    else:
        return ''

@register.filter
def format_date(start_date: datetime) -> str:
    """
    Format for search facets (year-month)
    """
    return start_date.strftime('%Y-%m')

@register.filter
def date_range_query(start_date: datetime, date_format='%Y-%m-%d') -> str:
    """
    Monthly range
    """
    return start_date.strftime(date_format) + ',' + (start_date + relativedelta(months=1)).strftime(date_format)


@register.filter
def search_url(query):
    return reverse('haystack_search') + '?q=' + urlencode(query)
