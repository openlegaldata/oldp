"""Allowlist HTML sanitizer for ingested case/law content.

``Case.content`` / ``Law.content`` are HTML from external scrapers and the write
API and are rendered raw in the detail templates. Without sanitization a stored
``<script>`` / ``<img onerror>`` / ``<a onclick>`` executes in a viewer's browser
(notably a staff reviewer previewing pending content) — stored XSS.

We sanitize the *final* rendered HTML — i.e. after the reference/annotation
markers have been spliced in by :func:`oldp.apps.lib.markers.insert_markers`.
Sanitizing before marker insertion is not viable: markers are offset-based and
annotation markers do not re-anchor, so shifting the content would misplace them.
Sanitizing after insertion means the trusted marker markup must survive the
allowlist, which is why the reference marker no longer carries an inline
``onclick`` (it is bound via event delegation in main.js) — inline event handlers
are stripped here by design.
"""

import nh3

# Tags legitimately used in German court decisions / statutes, plus the elements
# the reference (``<a class="ref">``) and annotation (``<span class="marker">``)
# markers inject at render time. Everything else (script, iframe, style, form,
# object, embed, ...) is dropped.
ALLOWED_TAGS = {
    "p",
    "br",
    "hr",
    "div",
    "span",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "b",
    "strong",
    "i",
    "em",
    "u",
    "s",
    "sub",
    "sup",
    "small",
    "mark",
    "ul",
    "ol",
    "li",
    "dl",
    "dt",
    "dd",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "caption",
    "colgroup",
    "col",
    "a",
    "blockquote",
    "pre",
    "code",
    "cite",
    "abbr",
    "q",
}

# Per-tag attribute allowlist. ``data-marker-id`` + ``class`` back the reference
# markers; ``id``/``class``/``style`` back the annotation markers. No event
# handlers (``on*``) are ever allowed.
ALLOWED_ATTRIBUTES = {
    # ``rel`` is managed by nh3 via ``link_rel`` below, so it must not be listed
    # here (nh3 rejects that combination).
    "a": {"href", "title", "class", "name", "target", "data-marker-id"},
    "span": {"class", "id", "style", "data-marker-id"},
    "div": {"class", "id"},
    "ol": {"style", "type", "start"},
    "ul": {"type"},
    "li": {"value"},
    "table": {"class"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "col": {"span"},
    "colgroup": {"span"},
}

# Only these CSS properties survive inside a ``style`` attribute (annotation
# highlight colour; legacy list styling). Everything else is stripped, so a
# ``style`` cannot be used for CSS-based UI redressing / data exfiltration.
ALLOWED_STYLE_PROPERTIES = {"background-color", "list-style-type"}

# Absolute URLs are limited to these schemes; relative links (``/case/123``) and
# fragments (``#refs``) are preserved. ``javascript:`` / ``data:`` are rejected.
ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


def sanitize_html(value: str) -> str:
    """Return ``value`` with all non-allowlisted HTML removed.

    Strips scripts, event handlers, ``javascript:`` URLs and disallowed
    tags/attributes/CSS while preserving legitimate legal-document markup and the
    trusted reference/annotation marker elements. Safe to call on empty/None-ish
    input (returned unchanged).
    """
    if not value:
        return value
    return nh3.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        filter_style_properties=ALLOWED_STYLE_PROPERTIES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
        strip_comments=True,
    )
