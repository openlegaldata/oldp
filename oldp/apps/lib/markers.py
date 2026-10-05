import html
import logging
import re
from typing import List, Tuple

from django.utils.html import strip_tags
from refex.document import normalize as refex_normalize

logger = logging.getLogger(__name__)


def _slice_to_plain(value: str) -> str:
    r"""Project a raw ``content`` slice to its plain-text form for
    integrity comparison against a marker's expected text.

    Mirrors the parts of refex's HTML normalization that affect short
    citation spans: HTML entities are decoded (``&#167;`` → ``§``) and
    inline tags are stripped (Wolters Kluwer RDFa ``<span>`` wrappers
    around a section, ``<em>`` emphasis, etc.). Whitespace is left
    intact — refex preserves ``\xa0`` and inner spaces inside
    citations and we match on that exact form.
    """
    return html.unescape(strip_tags(value))


def _collapse_whitespace(value: str) -> str:
    r"""Collapse every whitespace run (incl. newlines and ``\xa0``) to one space."""
    return " ".join(value.split())


def _slice_matches(raw_slice: str, expected: str) -> bool:
    r"""Whether a raw ``content`` slice holds the marker's expected text.

    The expected text is refex's plain-text projection of the citation,
    produced by its HTML normalizer: block-level tags become newlines and
    runs of spaces collapse. A plain ``strip_tags`` + ``unescape`` of the
    raw slice therefore differs whenever the citation spans a block
    boundary (``7<br>Am`` → ``"7Am"`` vs ``"7\nAm"``) or the raw HTML
    carries doubled spaces (``Abs.  2`` vs ``Abs. 2``), even though the
    offsets are correct. So after the exact comparison fails, normalize
    the slice the way refex does and compare whitespace-insensitively —
    a whitespace-only difference cannot point at a different citation.
    """
    if _slice_to_plain(raw_slice) == expected:
        return True
    return _collapse_whitespace(
        refex_normalize(raw_slice, "html")
    ) == _collapse_whitespace(expected)


_ENTITY_TAIL = re.compile(r"&#?\w{0,10}$")


def _extend_over_cut_entity(content: str, end: int) -> int:
    """Move ``end`` past an HTML entity the slice ``content[:end]`` cuts.

    When a citation's last character is entity-encoded in the raw HTML
    (``GO&Auml;`` for ``GOÄ``), refex maps it to the entity's ``&``, so the
    stored end offset stops right after the ``&``. Extend it to include
    the whole entity; otherwise return ``end`` unchanged.
    """
    match = _ENTITY_TAIL.search(content, max(0, end - 11), end)
    if match is None:
        return end
    semi = content.find(";", end, match.start() + 12)
    if semi < 0:
        return end
    entity = content[match.start() : semi + 1]
    if html.unescape(entity) == entity:
        return end
    return semi + 1


def _overlaps(start: int, end: int, spans: List[Tuple[int, int]]) -> bool:
    return any(start < s_end and s_start < end for s_start, s_end in spans)


def _find_marker_raw_span(
    content: str,
    marker_text: str,
    hint_start: int,
    taken: List[Tuple[int, int]] | None = None,
) -> Tuple[int, int] | None:
    r"""Locate the raw-content span matching ``marker_text``.

    Stored marker offsets sometimes drift out of sync with
    ``case.content`` — either because the case was re-imported with a
    different HTML-entity encoding (``&#167;`` vs ``§``) or because a
    later content edit shifted the rest of the document. The render-
    time guard in :func:`insert_markers` falls back to this helper to
    recover the citation: it tries the literal ``marker_text`` plus a
    small set of common HTML-entity inversions for the two characters
    refex normalizes most often in German legal text (``§`` and
    ``\\xa0`` non-breaking space), and returns the occurrence closest
    to ``hint_start``. Occurrences overlapping a span in ``taken`` (held
    by another marker whose offsets verified) are ignored, so a stale
    marker can't be re-anchored onto a sibling citation with the same
    text — the resulting overlap would drop both links.

    Returns the ``(start, end)`` raw-content span on success, or
    ``None`` when nothing matches — in which case the marker is
    skipped (preserving the #228 "no broken anchor around random word
    fragments" invariant).
    """
    candidates = {marker_text}
    if "§" in marker_text:
        candidates.add(marker_text.replace("§", "&#167;"))
    if "\xa0" in marker_text:
        candidates.add(marker_text.replace("\xa0", "&#160;"))
    if "§" in marker_text and "\xa0" in marker_text:
        candidates.add(marker_text.replace("§", "&#167;").replace("\xa0", "&#160;"))

    best: Tuple[int, int, int] | None = None
    for cand in candidates:
        if not cand:
            continue
        idx = 0
        while True:
            pos = content.find(cand, idx)
            if pos < 0:
                break
            idx = pos + 1
            if taken and _overlaps(pos, pos + len(cand), taken):
                continue
            dist = abs(pos - hint_start)
            if best is None or dist < best[0]:
                best = (dist, pos, pos + len(cand))
    if best is None:
        return None
    return best[1], best[2]


class BaseMarker(object):
    def get_start_position(self) -> int:
        raise NotImplementedError()

    def get_end_position(self) -> int:
        raise NotImplementedError()

    def get_marker_open_format(self) -> str:
        """Format of opening tag, e.g. [ref={uuid}]. Available placeholders: all marker class attributes.

        :return: format string
        """
        raise NotImplementedError()

    def get_marker_close_format(self) -> str:
        """Format of opening tag, e.g. [/ref]. Available placeholders: all marker class attributes.

        :return: format string
        """
        raise NotImplementedError()

    def get_marker_open(self):
        return self.get_marker_open_format().format(**self.__dict__)

    def get_marker_close(self):
        return self.get_marker_close_format().format(**self.__dict__)

    def get_expected_text(self) -> str | None:
        """Canonical text the marker's (start, end) slice should match.

        Returning ``None`` opts out of the integrity check in
        :func:`insert_markers`. Subclasses that persist the wrapped
        citation text alongside the offsets should override this so
        stored offsets that drift out of sync with ``content`` (e.g.
        because ``case.content`` was modified without re-running
        reference extraction) are skipped instead of producing broken
        ``<a>`` tags around random word fragments.
        """
        return None

    def insert_marker(self, content, marker_offset) -> Tuple[str, int]:
        """Replace the original content with markers, e.g. [ref]xy[/ref].

        :param content: Original content
        :param marker_offset: Offset from previous markers
        :return: Content with markers
        """
        start = self.get_start_position() + marker_offset
        end = self.get_end_position() + marker_offset

        # marker_open = '[ref=%i]' % key
        # Instead of key use uuid
        marker_open = self.get_marker_open()
        marker_close = self.get_marker_close()

        marker_offset += len(marker_open) + len(marker_close)

        # double replacements
        # alternative: content[start:end]
        content = (
            content[:start]
            + marker_open
            + content[start:end]
            + marker_close
            + content[end:]
        )

        return content, marker_offset


def insert_markers(content: str, markers: List[BaseMarker]):
    """Insert markers into content.

    Two-phase: first resolve each marker's effective ``(start, end)``
    for this render (with re-anchor on offset drift), then sort by
    start, detect overlaps, and splice the open/close tokens in.

    :param content: Without markers
    :param markers:
    :return:
    """
    # Phase 1: resolve effective offsets per marker.
    # For markers with an expected text (ReferenceMarker rows that
    # captured the citation text at extraction time): verify the slice
    # matches; if not, fuzzy-search content for the citation and re-
    # anchor. Skip when neither path lands a match. Stale markers are
    # re-anchored only after every verified marker is known, so they
    # can't land on a span a verified marker already holds.
    resolved: List[Tuple[int, int, BaseMarker]] = []
    stale: List[Tuple[int, int, BaseMarker, str]] = []
    for marker in markers:
        start = marker.get_start_position()
        end = marker.get_end_position()
        expected = marker.get_expected_text()
        if expected is not None:
            end = _extend_over_cut_entity(content, end)
            if not _slice_matches(content[start:end], expected):
                stale.append((start, end, marker, expected))
                continue
        resolved.append((start, end, marker))

    taken = [(start, end) for start, end, _marker in resolved]
    for start, end, marker, expected in stale:
        found = _find_marker_raw_span(content, expected, start, taken)
        if found is None:
            logger.warning(
                "Skipping stale marker %s: expected %r at [%d:%d] "
                "but found %r; no fallback match in content",
                marker,
                expected,
                start,
                end,
                _slice_to_plain(content[start:end]),
            )
            continue
        logger.info(
            "Re-anchored stale marker %s: stored [%d:%d] -> render [%d:%d]",
            marker,
            start,
            end,
            found[0],
            found[1],
        )
        resolved.append((found[0], found[1], marker))
        taken.append(found)

    # Phase 2: order by position, drop overlaps, splice.
    resolved.sort(key=lambda triple: triple[0])

    marker_offset = 0
    content_with_markers = content
    for i, (start, end, marker) in enumerate(resolved):
        # Check on overlaps. Spans are end-exclusive (``content[start:end]``
        # half-open slices), so two *adjacent* markers ``[a, b)`` and
        # ``[b, c)`` share no character and must both render — only a true
        # overlap (a shared character) is dropped. Hence strict ``>`` / ``<``:
        # a touching boundary (``prev_end == start``) is fine; ``prev_end >
        # start`` is a real overlap.
        if i > 0 and resolved[i - 1][1] > start:
            logger.error("Marker overlaps with previous marker: %s" % marker)
            continue
        if i + 1 < len(resolved) and resolved[i + 1][0] < end:
            logger.error("Marker overlaps with next marker: %s" % marker)
            continue

        adjusted_start = start + marker_offset
        adjusted_end = end + marker_offset
        marker_open = marker.get_marker_open()
        marker_close = marker.get_marker_close()
        marker_offset += len(marker_open) + len(marker_close)

        content_with_markers = (
            content_with_markers[:adjusted_start]
            + marker_open
            + content_with_markers[adjusted_start:adjusted_end]
            + marker_close
            + content_with_markers[adjusted_end:]
        )

    return content_with_markers
