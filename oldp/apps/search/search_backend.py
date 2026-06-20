import copy
import logging
import warnings

import haystack
from django.conf import settings as django_settings
from haystack.backends import BaseEngine
from haystack.backends.elasticsearch7_backend import (
    Elasticsearch7SearchBackend,
    Elasticsearch7SearchQuery,
)
from haystack.constants import DEFAULT_OPERATOR, FUZZINESS

logger = logging.getLogger(__name__)


def _deep_merge(base, override):
    """Recursively merge ``override`` into ``base`` (both dicts), in place.

    Nested dicts are merged key-by-key rather than replaced wholesale, so
    adding (for example) one custom analyzer under
    ``settings.analysis.analyzer`` does not wipe out haystack's built-in
    ngram/edgengram analyzers living under the same key. Non-dict values
    (and dict-over-non-dict mismatches) are overwritten.
    """
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


class SearchBackend(Elasticsearch7SearchBackend):
    exact_boost_factor = 3

    # Free-text fields that should use the German analyzer (``german_legal``,
    # defined in ``settings.ELASTICSEARCH_INDEX_SETTINGS``) instead of
    # haystack's default "snowball" (English) analyzer. Deliberately scoped:
    # the citation / structural fields (``cited_laws``, ``cited_cases``,
    # ``slug``, the ``*_exact`` facets, ``django_ct`` …) carry tokens or
    # keywords that German stemming would corrupt — e.g. it would mangle the
    # ``"{book_slug}__{section_slug}"`` cited-law tokens and break the
    # citation filter. Only human-readable prose gets the German treatment.
    GERMAN_TEXT_FIELDS = ("text", "title", "exact_matches")

    def __init__(self, connection_alias, **connection_options):
        # ``settings.ELASTICSEARCH_TIMEOUT`` is the canonical knob —
        # falls back to whatever was in ``HAYSTACK_CONNECTIONS[...]
        # ["TIMEOUT"]`` for callers that set it the old way. Done before
        # super().__init__ because the parent's ``__init__`` constructs
        # the ES client with ``timeout=self.timeout`` and never re-reads
        # it after that.
        es_timeout = getattr(django_settings, "ELASTICSEARCH_TIMEOUT", None)
        if es_timeout is not None:
            connection_options["TIMEOUT"] = int(es_timeout)

        super().__init__(connection_alias, **connection_options)
        # Merge ELASTICSEARCH_INDEX_SETTINGS from Django settings into DEFAULT_SETTINGS
        custom_settings = getattr(django_settings, "ELASTICSEARCH_INDEX_SETTINGS", None)
        if custom_settings:
            # Deep-merge so our analysis block (german_legal analyzer +
            # german_light_stem filter) is *added* to haystack's defaults
            # rather than replacing them — otherwise the built-in
            # ngram/edgengram analyzers (used by autocomplete) disappear and
            # index creation fails on EdgeNgram fields.
            merged = copy.deepcopy(self.DEFAULT_SETTINGS)
            _deep_merge(merged["settings"], custom_settings.get("settings", {}))
            self.DEFAULT_SETTINGS = merged

    def build_schema(self, fields):
        """Apply the German analyzer to free-text fields.

        Haystack maps every ``text`` field to its default English
        ("snowball") analyzer. We override the analyzer to ``german_legal``
        for the human-prose fields only (see ``GERMAN_TEXT_FIELDS``),
        leaving citation/structural/keyword fields untouched so the
        citation filter and facets keep working.

        .. warning::
            This MUST be deployed together with a reindex. ES analyzers are
            immutable on an existing index, so on an index created before
            this change Haystack's ``setup()`` will try to ``put_mapping``
            the ``german_legal`` analyzer, ES returns 400 (analyzer not
            found in the index settings), and because ``SILENTLY_FAIL`` is
            False the live search path raises on the first query. Run
            ``manage.py rebuild_index`` (recreates the index with the new
            settings) as part of the same rollout window. See
            ``internal-tools/docs/search/improvements-overview.md`` →
            "Analyzer rollout".
        """
        content_field_name, mapping = super().build_schema(fields)
        for field_name in self.GERMAN_TEXT_FIELDS:
            field = mapping.get(field_name)
            if field and field.get("type") == "text":
                field["analyzer"] = "german_legal"
                # Query-time-only colloquial->technical expansion. Distinct
                # search_analyzer means documents keep their german_legal
                # tokens (no re-index needed for synonym tweaks) while
                # queries get the concept_synonyms layer. See
                # ``settings.CONCEPT_SYNONYMS``.
                field["search_analyzer"] = "german_legal_search"
        return content_field_name, mapping

    def extract_file_contents(self, file_obj):
        pass

    def is_navigational_query(self, query_string):
        """Navigational queries do not contain operators (OR, AND, ...) and less than 4 words"""
        q_words = query_string.lower().split()

        # Contains OR, AND, ...
        for word in self.RESERVED_WORDS:
            if word.lower() in q_words:
                return False

        if len(q_words) >= 4:
            return False

        # logger.debug('Using boost for navigational queries')

        return True

    def build_search_kwargs(
        self,
        query_string,
        sort_by=None,
        start_offset=0,
        end_offset=None,
        fields="",
        highlight=False,
        facets=None,
        date_facets=None,
        query_facets=None,
        narrow_queries=None,
        spelling_query=None,
        within=None,
        dwithin=None,
        distance_point=None,
        models=None,
        limit_to_registered_models=None,
        result_class=None,
        **extra_kwargs,
    ):
        # NOTE: `models` and `limit_to_registered_models` are accepted for
        # signature compatibility with the parent class but intentionally
        # ignored. The override below replaces the parent body wholesale and
        # never re-introduces Haystack's django_ct narrow-query, so callers
        # of `SearchQuerySet.models(...)` get no model isolation in real ES.
        # The codebase compensates by filtering on `facet_model_name_exact`
        # at the call site (see SearchSchemaFilter, search_laws, search_cases).
        # If you re-add the model narrowing here, drop the workaround filters.
        # logger.debug("build_search_kwargs ... ")

        index = haystack.connections[self.connection_alias].get_unified_index()
        content_field = index.document_field

        if query_string == "*:*":
            kwargs = {"query": {"match_all": {}}}
        else:
            if self.is_navigational_query(query_string):
                # Boost the exact navigational target (e.g. ``BGB 123`` → the
                # § 123 BGB law doc) while NOT letting the boost clause widen
                # the result set with loose term matches.
                #
                # ``exact_matches`` stores a doc's full navigational forms —
                # ``"<code> <section>"``, the reversed and no-space variants,
                # and the title (see ``LawIndex.prepare_exact_matches``). It
                # is deliberately a ``should`` *alternative* (not just a score
                # boost on top of ``query_string``): a law section's ``text``
                # field almost never contains its own section number, so
                # ``/search/?q="bgb 123"`` can only surface § 123 BGB via this
                # clause — requiring a ``query_string`` (text) match would drop
                # the law entirely.
                #
                # The clause MUST be ``match_phrase``, never a plain ``match``.
                # A plain ``match`` ORs the analysed terms, so a multi-word /
                # phrase query matched any doc whose ``exact_matches`` (incl.
                # the law *title*) shared a single common word — e.g.
                # ``"Glauben und Treu"`` matched every title containing "und"
                # (~10k docs) on surfaces whose main query carries no extra
                # in-query filter (the web search form; REST/MCP incidentally
                # serialize ``review_status:accepted`` into the query string,
                # flipping them onto the non-navigational path). ``match_phrase``
                # only matches the full query as a consecutive phrase against
                # the stored navigational forms, so it boosts the real target
                # without leaking. ``query_string`` remains the general matcher.
                kwargs = {
                    "query": {
                        "bool": {
                            "should": [
                                {
                                    "query_string": {
                                        "default_field": content_field,
                                        "default_operator": DEFAULT_OPERATOR,
                                        "query": query_string,
                                        "analyze_wildcard": True,
                                        # "auto_generate_phrase_queries": True,
                                        "fuzziness": FUZZINESS,
                                    }
                                },
                                {
                                    "match_phrase": {
                                        "exact_matches": {
                                            "query": query_string,
                                            "boost": self.exact_boost_factor,
                                        }
                                    }
                                },
                            ]
                        }
                    }
                }
            else:
                kwargs = {
                    "query": {
                        "query_string": {
                            "default_field": content_field,
                            "default_operator": DEFAULT_OPERATOR,
                            "query": query_string,
                            "analyze_wildcard": True,
                            # "auto_generate_phrase_queries": True,
                            "fuzziness": FUZZINESS,
                        }
                    }
                }

        filters = []

        if fields:
            if isinstance(fields, (list, set)):
                fields = " ".join(fields)

            kwargs["stored_fields"] = fields

        if sort_by is not None:
            order_list = []
            for field, direction in sort_by:
                if field == "distance" and distance_point:
                    # Do the geo-enabled sort.
                    lng, lat = distance_point["point"].coords
                    sort_kwargs = {
                        "_geo_distance": {
                            distance_point["field"]: [lng, lat],
                            "order": direction,
                            "unit": "km",
                        }
                    }
                else:
                    if field == "distance":
                        warnings.warn(
                            "In order to sort by distance, you must call the '.distance(...)' method."
                        )

                    # Regular sorting.
                    sort_kwargs = {field: {"order": direction}}

                order_list.append(sort_kwargs)

            kwargs["sort"] = order_list

        # From/size offsets don't seem to work right in Elasticsearch's DSL. :/
        # if start_offset is not None:
        #     kwargs['from'] = start_offset

        # if end_offset is not None:
        #     kwargs['size'] = end_offset - start_offset

        if highlight:
            # `highlight` can either be True or a dictionary containing custom parameters
            # which will be passed to the backend and may override our default settings:

            kwargs["highlight"] = {
                # ES rejects highlighting on fields longer than
                # index.highlight.max_analyzed_offset (default 1MB). A few
                # case texts exceed this and surfaced as
                # search_phase_execution_exception 400s. Setting the per-query
                # offset limit lets ES truncate analysis of long docs instead.
                "max_analyzed_offset": 1_000_000,
                "fields": {content_field: {}},
            }

            if isinstance(highlight, dict):
                kwargs["highlight"].update(highlight)

        if self.include_spelling:
            kwargs["suggest"] = {
                "suggest": {
                    "text": spelling_query or query_string,
                    "term": {
                        # Using content_field here will result in suggestions of stemmed words.
                        "field": "_all"
                    },
                }
            }

        if narrow_queries is None:
            narrow_queries = set()

        if facets is not None:
            kwargs.setdefault("aggs", {})

            for facet_fieldname, extra_options in facets.items():
                facet_options = {
                    "meta": {"_type": "terms"},
                    "terms": {"field": index.get_facet_fieldname(facet_fieldname)},
                }
                if "order" in extra_options:
                    facet_options["meta"]["order"] = extra_options.pop("order")
                # Special cases for options applied at the facet level (not the terms level).
                if extra_options.pop("global_scope", False):
                    # Renamed "global_scope" since "global" is a python keyword.
                    facet_options["global"] = True
                if "facet_filter" in extra_options:
                    facet_options["facet_filter"] = extra_options.pop("facet_filter")
                facet_options["terms"].update(extra_options)
                kwargs["aggs"][facet_fieldname] = facet_options

        if date_facets is not None:
            kwargs.setdefault("aggs", {})

            for facet_fieldname, value in date_facets.items():
                # Need to detect on gap_by & only add amount if it's more than one.
                interval = value.get("gap_by").lower()

                # Need to detect on amount (can't be applied on months or years).
                if value.get("gap_amount", 1) != 1 and interval not in (
                    "month",
                    "year",
                ):
                    # Just the first character is valid for use.
                    interval = "%s%s" % (value["gap_amount"], interval[:1])

                kwargs["aggs"][facet_fieldname] = {
                    "meta": {"_type": "date_histogram"},
                    "date_histogram": {"field": facet_fieldname, "interval": interval},
                    "aggs": {
                        facet_fieldname: {
                            "date_range": {
                                "field": facet_fieldname,
                                "ranges": [
                                    {
                                        "from": self._from_python(
                                            value.get("start_date")
                                        ),
                                        "to": self._from_python(value.get("end_date")),
                                    }
                                ],
                            }
                        }
                    },
                }

        if query_facets is not None:
            kwargs.setdefault("aggs", {})

            for facet_fieldname, value in query_facets:
                kwargs["aggs"][facet_fieldname] = {
                    "meta": {"_type": "query"},
                    "filter": {"query_string": {"query": value}},
                }

        for q in narrow_queries:
            filters.append({"query_string": {"query": q}})

        if within is not None:
            filters.append(self._build_search_query_within(within))

        if dwithin is not None:
            filters.append(self._build_search_query_dwithin(dwithin))

        # Drop stale law revisions at ES query time. ``LawIndex.is_latest``
        # mirrors ``book.latest``; without this clause, ES returns docs
        # for old book revisions that ``LawIndex.read_queryset`` later
        # filters out at hydration time, which made haystack scan
        # chunk-by-chunk through thousands of stale hits (247 ES
        # round-trips for ``/search/?q=BGB`` before this filter).
        #
        # Excluding only ``is_latest=false`` (not missing-or-false) keeps
        # docs from before the ``is_latest`` field was added — they will
        # still be returned until the next reindex populates the field,
        # so deploying this filter is safe to do before the reindex.
        # Cases pass through untouched (CaseIndex has no ``is_latest``).
        filters.append(
            {
                "bool": {
                    "must_not": {
                        "bool": {
                            "must": [
                                {"term": {"django_ct": "laws.law"}},
                                {"term": {"is_latest": False}},
                            ]
                        }
                    }
                }
            }
        )

        # if we want to filter, change the query type to bool
        if filters:
            kwargs["query"] = {"bool": {"must": kwargs.pop("query")}}
            if len(filters) == 1:
                kwargs["query"]["bool"]["filter"] = filters[0]
            else:
                kwargs["query"]["bool"]["filter"] = {"bool": {"must": filters}}

        if extra_kwargs:
            kwargs.update(extra_kwargs)

        # logger.debug('ES query: %s' % json.dumps(kwargs, indent=4))

        return kwargs


class SearchEngine(BaseEngine):
    """Custom Elasticsearch 7 search engine"""

    backend = SearchBackend
    query = Elasticsearch7SearchQuery
