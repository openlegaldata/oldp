from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from haystack import indexes

from oldp.apps.laws.models import Law

# Registers "Law" as a translatable msgid for the search facet label
# rendered by oldp.apps.search.views._build_facets via gettext(value).
# Cases get the equivalent treatment via SortableColumn(_("Case"), ...) in
# oldp.apps.cases.views.
_FACET_LABEL = _("Law")


class LawIndex(indexes.SearchIndex, indexes.Indexable):
    """# Define files that will be excluded in JSON export / Elasticsearch document
    es_fields_exclude = ['content', 'amtabk', 'footnotes', 'doknr']
    es_type = 'law'

    """

    FACET_MODEL_NAME = "Law"

    text = indexes.CharField(document=True, use_template=True)
    slug = indexes.CharField(model_attr="slug")
    review_status = indexes.CharField(model_attr="review_status")
    title = indexes.CharField()
    absolute_url = indexes.CharField()
    model_type = indexes.CharField()
    facet_model_name = indexes.CharField(faceted=True)
    book_code = indexes.CharField(faceted=True)

    # title_auto = indexes.EdgeNgramField()
    exact_matches = indexes.CharField()  # boost on exact match with this field
    # ``is_latest`` mirrors ``book.latest`` so the search backend can
    # filter stale (non-latest) law docs out at ES query time. Without
    # this, after a book revision lands the old revision's docs still
    # live in ES until the next reindex; haystack's read_queryset then
    # drops them at hydration time and silently retries the next ES
    # chunk, looping chunk-by-chunk for popular books (BGB ~92% stale
    # docs caused 247 ES round-trips per /search/?q=BGB request).
    is_latest = indexes.BooleanField()

    def get_model(self):
        return Law

    def prepare_is_latest(self, obj):
        return bool(obj.book and obj.book.latest)

    def prepare_title(self, obj):
        return obj.get_title()

    def prepare_absolute_url(self, obj):
        return obj.get_absolute_url()

    def prepare_model_type(self, obj):
        return "Law"

    def prepare_facet_model_name(self, obj):
        return self.FACET_MODEL_NAME

    def prepare_book_code(self, obj):
        return obj.book.code

    def prepare_exact_matches(self, obj):
        """All possible navigational queries"""
        sect = slugify(obj.section)
        code = obj.book.code.lower()

        return [
            code + " " + sect,
            sect + " " + code,
            # no whitespace
            code + sect,
            sect + code,
            obj.title,
        ]

    def index_queryset(self, using=None):
        # Indexing all accepted laws (including non-latest revisions)
        # rather than only the latest is intentional. The earlier
        # ``filter(book__latest=True)`` shape meant that when a new book
        # revision landed, the old revision's ES docs were orphaned
        # until someone ran ``update_index --remove`` — and in the
        # interim they still scored on text matches, but
        # ``LawIndex.read_queryset`` filtered them out at hydration time,
        # forcing haystack into a chunk-by-chunk skip loop (~247 ES
        # round-trips for ``/search/?q=BGB``). Indexing both revisions
        # lets the next ``update_index`` re-mark the old docs with
        # ``is_latest=false``; the search backend then filters them out
        # at ES query time, which is what users actually want.
        return (
            self.get_model()
            .objects.filter(review_status="accepted")
            .select_related("book")
        )
