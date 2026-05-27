"""Helpers shared across MCP tool modules.

Functions here are stateless utilities that several toolsets need —
limit clamping, response shaping, etc. Per-toolset logic stays in the
respective ``apps/<name>/mcp.py``.
"""

from __future__ import annotations


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
