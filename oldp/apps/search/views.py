import logging

from django.http import JsonResponse
from django.utils.translation import ugettext_lazy as _
from haystack.generic_views import SearchView
from haystack.query import SearchQuerySet

logger = logging.getLogger(__name__)


class CustomSearchView(SearchView):
    """Custom search view for haystack."""

    def get_context_data(self, *args, **kwargs):
        context = super(CustomSearchView, self).get_context_data(*args, **kwargs)

        context.update({
            'title': _('Search') + ' ' + context['query'][:30]
        })

        return context


def autocomplete_view(request):
    """Stub for auto-complete feature (title for all objects missing)"""
    suggestions_limit = 5
    sqs = SearchQuerySet().autocomplete(content_auto=request.GET.get('q', ''))[:suggestions_limit]

    suggestions = [{'title': result.title, 'url': result.object.get_absolute_url()} for result in sqs]

    return JsonResponse({
        'results': suggestions
    })
