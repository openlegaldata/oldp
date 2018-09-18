from math import ceil

from django.conf import settings
from django.core.paginator import Paginator
from django.utils.functional import cached_property


class LimitedPaginator(Paginator):
    """Limits the number of pages to avoid slow DB queries"""
    @cached_property
    def num_pages(self):
        """Return the total number of pages."""
        if self.count == 0 and not self.allow_empty_first_page:
            return 0
        hits = max(1, self.count - self.orphans)
        return min(settings.PAGINATE_UNTIL, ceil(hits / self.per_page))

