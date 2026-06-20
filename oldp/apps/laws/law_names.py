"""Law full-name → abbreviation (book code) synonyms, derived from data.

German laws are cited in case text almost exclusively by their *code*
(``KSchG``, ``BetrVG``, ``BGB``), but laypeople search by the full name
(``Kündigungsschutzgesetz``). Without a bridge those queries miss the cases:
``Kündigungsschutzgesetz`` ≈ 2.9k hits vs ``KSchG`` ≈ 9k.

The bridge is a query-time ``synonym_graph`` (directional ``name => name,
code``) on the German search analyzer — the same mechanism as the colloquial
concept synonyms (#14). It must be the analyzer (not a query rewrite):
Haystack's ``AutoQuery`` escapes boolean ``OR`` / parentheses, so a rewritten
``(name OR code)`` query degrades to a literal-term search. A synonym filter's
per-query cost is O(query length), independent of the rule count, so this does
NOT regress response times — the cost is paid once at analyzer-build time.

This module builds the map *principally* from the ``LawBook`` table (no
hand-curated per-law list) and emits the synonym rules. A management command
(``generate_law_synonyms``) materialises them to a file that the analyzer
loads (the analyzer is configured at settings time, before the DB is
reachable, so the rules cannot be queried live — they are generated offline,
like the curated synonym vocabulary).
"""

import re

# Title suffixes that mark a genuine law *name* (vs a descriptive title like
# "Gesetz über die …", which starts — not ends — with "Gesetz"). Restricting
# to these keeps the map to canonical names whose code is a real citation
# abbreviation. Lowercase; matched with ``str.endswith``.
_LAW_NAME_SUFFIXES = (
    "gesetzbuch",
    "gesetz",
    "verordnung",
    "ordnung",
    "vertrag",
    "abkommen",
    "buch",
    "satzung",
    "statut",
    "konvention",
)

# Canonical law names are short (1-2 words). A long multi-word title that
# merely ends in a law suffix is a descriptive title, not a citation name —
# exclude it.
_MAX_NAME_WORDS = 4

# A code may carry a trailing revision token, e.g. ``"BDSG 1990"`` /
# ``"TabStG 2009"``; the citation abbreviation is the part before the year.
# Codes whose suffix is NOT a year (``"SGB V"``) are kept intact.
_VERSION_SUFFIX = re.compile(r"\s+\d{4}.*$")


def _base_code(code):
    return _VERSION_SUFFIX.sub("", (code or "").strip())


def _is_law_name(title_lower):
    return title_lower.endswith(_LAW_NAME_SUFFIXES)


def build_law_name_map():
    """Return ``{normalized_full_name: base_code}`` from the latest LawBooks.

    Only law-name-shaped titles (see ``_LAW_NAME_SUFFIXES``) of ≤4 words with
    a base code of ≥2 chars are included (1-char codes are too ambiguous).
    Keys are lowercased + whitespace-collapsed; first write wins so the result
    is stable across runs.
    """
    from oldp.apps.laws.models import LawBook

    mapping = {}
    rows = (
        LawBook.objects.filter(latest=True, review_status="accepted")
        .values_list("title", "code")
        .iterator()
    )
    for title, code in rows:
        title = (title or "").strip()
        base = _base_code(code)
        if not title or len(base) < 2:
            continue
        words = title.lower().split()
        if len(words) > _MAX_NAME_WORDS:
            continue
        key = " ".join(words)
        if not _is_law_name(key) or key == base.lower():
            continue
        mapping.setdefault(key, base)
    return mapping


def law_synonym_rules(mapping=None):
    """Render the name→code map as directional ``synonym_graph`` rules.

    Each rule is ``"<name> => <name>, <code>"`` (lowercased, as the analyzer
    lowercases before the synonym filter). Directional so a *code* search is
    unaffected and precise/professional queries are never broadened — only the
    full-name query expands to also match the code that appears in case text.
    """
    if mapping is None:
        mapping = build_law_name_map()
    rules = []
    for name in sorted(mapping):
        code = mapping[name].lower()
        # RHS keeps the name so it still matches its own occurrences, plus the
        # code. synonym_graph handles the multi-word LHS / RHS ("sgb v").
        rules.append(f"{name} => {name}, {code}")
    return rules
