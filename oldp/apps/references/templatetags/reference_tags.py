"""Template helpers for rendering reference groups."""

from django import template

register = template.Library()


@register.filter
def distinct_marker_pks(ref_group, content):
    """Distinct marker pks for ``ref_group``, preserving order.

    The reference lists render one hidden ``<div class="ref-marker-id-N">`` per
    entry purely so the JS can locate markers, and several references routinely
    share one marker (an enumeration such as "§§ 3, 3b AsylG" is a single marker
    with N references). Emitting one element per *reference* is therefore
    redundant, and unbounded: a law whose citation ranges had expanded into
    67,888 rows rendered 67,904 divs — 7.4 MB — and timed out.

    Collapsing to distinct marker pks keeps the JS contract identical while
    making the output proportional to markers rather than references, so a
    future extraction defect degrades a count rather than taking the page down.

    ``content`` is the owning Case/Law, used to resolve the pks in one query.
    """
    try:
        pk_map = content.get_reference_marker_pk_map()
    except AttributeError:  # pragma: no cover - defensive
        return []

    seen = {}
    for ref in ref_group:
        pk = pk_map.get(getattr(ref, "pk", None))
        if pk is not None:
            seen[pk] = None
    return list(seen)
