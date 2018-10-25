from django import template
from haystack.models import SearchResult
from haystack.utils.highlighting import Highlighter

register = template.Library()


@register.filter
def get_search_snippet(search_result: SearchResult, query: str) -> str:
    hlr = Highlighter(query, html_tag='strong')

    text = search_result.get_stored_fields()['text']

    return hlr.highlight(text)
