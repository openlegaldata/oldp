"""Elasticsearch German-analysis settings, with externally-loaded synonyms.

The ``german_legal`` (index) and ``german_legal_search`` (query) analyzers
are generic German-language analysis. The *synonym vocabulary*, however, is
locale/deployment-specific curated data and must not live in the generic
``oldp`` app — it is loaded at settings time from a file whose path is given
by ``OLDP_SEARCH_SYNONYMS_FILE`` (see ``settings.py``). When no file is
configured, the analyzers simply run without synonym filters.

Pure module (stdlib only) so it can be imported from settings before the
Django app registry is ready, and unit-tested in isolation.
"""

import os


def load_search_synonyms(path):
    """Parse a sectioned synonyms file into ``(legal, concept)`` lists.

    File format (UTF-8): blank lines and ``# comment`` lines are ignored;
    ``[section]`` switches the active list (``legal_synonyms`` /
    ``concept_synonyms``); every other line is one Elasticsearch synonym
    rule. Returns two empty lists if ``path`` is falsy or missing.

    Args:
        path: Filesystem path to the synonyms file (or empty/None).

    Returns:
        ``(legal_synonyms, concept_synonyms)`` — lists of rule strings.
    """
    legal, concept = [], []
    if not path or not os.path.exists(path):
        return legal, concept

    bucket = {"legal_synonyms": legal, "concept_synonyms": concept}
    current = None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current = line[1:-1].strip()
                continue
            if current in bucket:
                bucket[current].append(line)
    return legal, concept


def build_german_index_settings(legal_synonyms, concept_synonyms):
    """Build ``ELASTICSEARCH_INDEX_SETTINGS`` for the German analyzers.

    Two custom analyzers: ``german_legal`` (index) and
    ``german_legal_search`` (query). Filter order is lowercase → synonyms →
    ``german_normalization`` → ``german_light_stem``. Synonym filters are
    included only when the corresponding list is non-empty:

    * ``legal_synonyms`` (bidirectional ``synonym``) — index + query;
    * ``concept_synonyms`` (directional ``synonym_graph``) — query only, so
      colloquial queries expand to legal vocabulary without broadening the
      precise/technical-term searches and without re-indexing documents.

    ``light_german`` (not snowball "german") is deliberate — it folds
    plurals/cases + normalizes umlauts without the over-stemming that
    collapses distinct lemmas (Kündigung -> "kundig"). No stopword filter:
    legal exact-phrase queries must keep function words.

    Args:
        legal_synonyms: Bidirectional equivalence rules (may be empty).
        concept_synonyms: Directional colloquial→legal rules (may be empty).

    Returns:
        The ``ELASTICSEARCH_INDEX_SETTINGS`` dict.
    """
    filters = {
        "german_light_stem": {"type": "stemmer", "language": "light_german"},
    }
    index_chain = ["lowercase"]
    search_chain = ["lowercase"]

    if legal_synonyms:
        filters["legal_synonyms"] = {"type": "synonym", "synonyms": legal_synonyms}
        index_chain.append("legal_synonyms")
        search_chain.append("legal_synonyms")
    if concept_synonyms:
        # synonym_graph (not plain synonym) so multi-word terms work
        # ("Hartz IV" -> "Arbeitslosengeld II"). Query-time only.
        filters["concept_synonyms"] = {
            "type": "synonym_graph",
            "synonyms": concept_synonyms,
        }
        search_chain.append("concept_synonyms")

    index_chain += ["german_normalization", "german_light_stem"]
    search_chain += ["german_normalization", "german_light_stem"]

    return {
        "settings": {
            "number_of_replicas": 0,
            "refresh_interval": "60s",
            "analysis": {
                "filter": filters,
                "analyzer": {
                    "german_legal": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": index_chain,
                    },
                    "german_legal_search": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": search_chain,
                    },
                },
            },
        }
    }
