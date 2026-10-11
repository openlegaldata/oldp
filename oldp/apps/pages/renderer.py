"""Render static pages from markdown files, cached so a file is parsed once
per process and only re-parsed when it changes on disk.

Markdown files live in ``settings.MARKDOWN_PAGES_DIR`` (overridable per theme,
e.g. the German texts ship in oldp-de). Each ``<slug>.md`` becomes the page at
``/pages/<slug>/``. An optional ``title:`` meta header (python-markdown ``meta``
extension) sets the page title; otherwise the first ``# H1`` or the slug is used.
"""

import re
from functools import lru_cache
from pathlib import Path

import markdown
from django.conf import settings
from django.utils.safestring import mark_safe

# Slug is already constrained to ``[\w-]+`` by the URLconf; this is defence in
# depth against path traversal if the renderer is ever called directly.
_SLUG_RE = re.compile(r"^[\w-]+$")

_MARKDOWN_EXTENSIONS = ["meta", "extra", "sane_lists", "smarty", "toc"]


class PageNotFound(Exception):
    """Raised when no markdown file exists for the given slug."""


def pages_dir() -> Path:
    return Path(settings.MARKDOWN_PAGES_DIR)


def _path_for(slug: str) -> Path:
    if not _SLUG_RE.match(slug):
        raise PageNotFound(slug)
    return pages_dir() / f"{slug}.md"


def _title_from(meta: dict, html: str, slug: str) -> str:
    if meta.get("title"):
        return " ".join(meta["title"])
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    if h1:
        return re.sub(r"<[^>]+>", "", h1.group(1)).strip()
    return slug.replace("-", " ").replace("_", " ").title()


@lru_cache(maxsize=64)
def _render(slug: str, _mtime: float) -> dict:
    """Parse ``<slug>.md`` to HTML. ``_mtime`` is part of the cache key only:
    when the file is edited its mtime changes, invalidating the cached entry.
    """
    text = _path_for(slug).read_text(encoding="utf-8")
    md = markdown.Markdown(extensions=_MARKDOWN_EXTENSIONS, output_format="html5")
    html = md.convert(text)
    meta = getattr(md, "Meta", {}) or {}
    return {
        "slug": slug,
        "title": _title_from(meta, html, slug),
        "html": mark_safe(html),
    }


def render_page(slug: str) -> dict:
    """Return ``{"slug", "title", "html"}`` for a slug, or raise PageNotFound.

    Rendering is memoised on the file's mtime, so repeated requests for the same
    page do not re-parse the markdown.
    """
    path = _path_for(slug)
    try:
        mtime = path.stat().st_mtime
    except OSError as e:
        raise PageNotFound(slug) from e
    return _render(slug, mtime)
