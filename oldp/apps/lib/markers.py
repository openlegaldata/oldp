import html
import logging
from typing import List, Tuple

from django.utils.html import strip_tags

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


def _find_marker_raw_span(
    content: str, marker_text: str, hint_start: int
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
    to ``hint_start``.

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
            dist = abs(pos - hint_start)
            if best is None or dist < best[0]:
                best = (dist, pos, pos + len(cand))
            idx = pos + 1
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
    # anchor. Skip when neither path lands a match.
    resolved: List[Tuple[int, int, BaseMarker]] = []
    for marker in markers:
        start = marker.get_start_position()
        end = marker.get_end_position()
        expected = marker.get_expected_text()
        if expected is not None:
            actual = _slice_to_plain(content[start:end])
            if actual != expected:
                found = _find_marker_raw_span(content, expected, start)
                if found is None:
                    logger.warning(
                        "Skipping stale marker %s: expected %r at [%d:%d] "
                        "but found %r; no fallback match in content",
                        marker,
                        expected,
                        start,
                        end,
                        actual,
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
                start, end = found
        resolved.append((start, end, marker))

    # Phase 2: order by position, drop overlaps, splice.
    resolved.sort(key=lambda triple: triple[0])

    marker_offset = 0
    content_with_markers = content
    for i, (start, end, marker) in enumerate(resolved):
        # Check on overlaps
        if i > 0 and resolved[i - 1][1] >= start:
            logger.error("Marker overlaps with previous marker: %s" % marker)
            continue
        if i + 1 < len(resolved) and resolved[i + 1][0] <= end:
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
