"""Helpers shared across MCP tool modules.

Functions here are stateless utilities that several toolsets need —
limit clamping, response shaping, etc. Per-toolset logic stays in the
respective ``apps/<name>/mcp.py``.
"""

from __future__ import annotations

import html
import re

from django.utils.html import strip_tags

# Closing tags / void elements after which a line break is inserted so the
# plain-text rendering keeps paragraph and heading boundaries.
_BLOCK_BREAK_RE = re.compile(
    r"(<br\s*/?>|</(?:p|div|h[1-6]|li|dd|dl|tr|table|blockquote|pre|ul|ol)>)",
    re.IGNORECASE,
)
# Closing tags followed by a space instead of a line break: a <dt> (list
# number, Randnummer) stays on the line of its <dd>, and a <sup> sentence
# number ("<sup>1</sup>Der ...") does not stick to the following word.
_INLINE_BREAK_RE = re.compile(r"(</(?:dt|sup|td|th)>)", re.IGNORECASE)
# A list opening inside a paragraph ("Der Einkommensteuer unterliegen <dl>")
# starts its first item on a new line.
_LIST_START_RE = re.compile(r"(<(?:dl|ul|ol)\b[^>]*>)", re.IGNORECASE)
_SOURCE_WHITESPACE_RE = re.compile(r"\s+")
_INLINE_WHITESPACE_RE = re.compile(r"[ \t\r\f\v\u00a0]+")


def clamp_limit(requested: int, *, maximum: int, minimum: int = 1) -> tuple[int, bool]:
    """Clamp ``requested`` to ``[minimum, maximum]``.

    Returns ``(clamped_value, was_clamped)``. Callers should surface
    ``was_clamped`` (and the original requested value) in their
    response so consumers can tell that the page they got back is
    smaller than the page they asked for — silent clamping was the UX
    issue this helper was introduced to fix.

    Negative or zero values clamp up to ``minimum``; values above
    ``maximum`` clamp down. The "was_clamped" flag is true in either
    case so the caller can include a hint in the payload.
    """
    if requested < minimum:
        return minimum, True
    if requested > maximum:
        return maximum, True
    return requested, False


def with_limit_meta(
    payload: dict, *, requested: int, applied: int, was_clamped: bool, maximum: int
) -> dict:
    """Annotate a response dict with limit-clamp metadata when relevant.

    Only adds ``requested_limit`` + ``limit_clamped`` + ``max_limit``
    when the caller's input was actually rewritten — un-clamped calls
    stay free of bookkeeping noise. Mutates and returns ``payload``.
    """
    if was_clamped:
        payload["requested_limit"] = requested
        payload["limit_clamped"] = True
        payload["max_limit"] = maximum
    return payload


def html_to_text(value: str | None) -> str:
    """Convert stored HTML content (cases, laws) to normalized plain text.

    Same approach as the search index (``Case.get_text`` /
    ``Law.get_text``: tags stripped, entities decoded, reference markers
    removed), plus whitespace normalization so the text is compact and
    readable: block-level elements end a line, list numbers stay on the
    line of their item, runs of spaces/tabs collapse to a single space,
    lines are stripped, and empty lines are dropped (one line per
    paragraph, heading, list item, ...). This is the ``content`` returned
    by the MCP retrieval tools and the coordinate system of their
    ``offset``/``length`` parameters, so it must be deterministic for a
    given input.

    Args:
        value: HTML string (may be ``None`` or empty).

    Returns:
        Plain text without markup.
    """
    if not value:
        return ""
    from oldp.apps.references.models import ReferenceMarker

    # Source line breaks/indentation are insignificant in HTML; only tags
    # decide where lines break.
    text = _SOURCE_WHITESPACE_RE.sub(" ", value)
    text = _LIST_START_RE.sub(r"\n\1", text)
    text = _BLOCK_BREAK_RE.sub(r"\1\n", text)
    text = _INLINE_BREAK_RE.sub(r"\1 ", text)
    # Strip tags *before* unescaping so escaped text such as "&lt;x&gt;"
    # survives as literal "<x>" instead of being removed as a tag.
    text = ReferenceMarker.remove_markers(html.unescape(strip_tags(text)))
    lines = (_INLINE_WHITESPACE_RE.sub(" ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def is_snippet_request(offset: int, length: int) -> bool:
    """Return whether the caller asked for a plain-text snippet.

    Any non-zero value counts, so invalid (negative) input is routed to
    :func:`text_snippet` and rejected there instead of being ignored.
    """
    return offset != 0 or length != 0


def text_snippet(full_text: str, *, offset: int, length: int) -> dict:
    """Slice plain text (the output of :func:`html_to_text`).

    Positions refer to characters of the plain text, not of the raw HTML.
    Callers paginate by passing ``next_offset`` back as ``offset`` until
    ``has_more`` is false.

    Args:
        full_text: Plain text as returned by :func:`html_to_text`.
        offset: Start position in plain-text characters (>= 0).
        length: Maximum number of characters to return; ``0`` returns
            everything from ``offset`` to the end.

    Returns:
        Dict with ``text`` (the snippet), ``offset``, ``length`` (actual
        length of ``text``), ``total_length`` (length of the whole plain
        text), ``has_more`` and ``next_offset`` (``None`` at the end).
        Negative arguments or an ``offset`` past the end yield an
        ``error`` payload instead.
    """
    if offset < 0 or length < 0:
        return {"error": "offset and length must be non-negative integers."}
    total = len(full_text)
    if offset > total:
        return {
            "error": (
                f"offset {offset} is beyond the end of the text (total_length={total})."
            ),
            "total_length": total,
        }
    end = total if length == 0 else min(offset + length, total)
    has_more = end < total
    return {
        "text": full_text[offset:end],
        "offset": offset,
        "length": end - offset,
        "total_length": total,
        "has_more": has_more,
        "next_offset": end if has_more else None,
    }
