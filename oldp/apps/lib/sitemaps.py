"""XML sitemaps, rendered to static files once a day.

Rendering a page of 50,000 cases takes longer than the gunicorn timeout, so
the sitemaps are not built per request. ``manage.py generate_sitemaps`` writes
them to ``settings.SITEMAP_ROOT``:

    sitemap.xml               index of all pages below
    sitemap-<section>-<n>.xml one page of a section (court, case, law)

The web server (or :func:`sitemap_file_view`) serves those files as they are.
See docs/sitemap-xml.md.
"""

import os
import re
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.sites.models import Site
from django.http import FileResponse, Http404
from django.template.loader import render_to_string
from django.utils.http import http_date

INDEX_FILENAME = "sitemap.xml"
# Matches the index and page filenames; the URL pattern uses the same regex.
FILENAME_RE = r"sitemap(?:-[a-z]+-[0-9]+)?\.xml"
PAGE_RE = re.compile(r"^sitemap-[a-z]+-[0-9]+\.xml$")


def get_sitemaps():
    """Sitemap sections, in the order they appear in the index."""
    from oldp.apps.cases.sitemaps import CaseSitemap
    from oldp.apps.courts.sitemaps import CourtSitemap
    from oldp.apps.laws.sitemaps import LawSitemap

    return {"court": CourtSitemap(), "case": CaseSitemap(), "law": LawSitemap()}


def page_filename(section, page):
    return f"sitemap-{section}-{page}.xml"


def _write(path, content):
    """Write ``content`` to ``path`` atomically, so a reader never sees half a file."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".xml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def generate_sitemaps(root=None, protocol="https", log=None):
    """Render every sitemap page and the index into ``root``.

    Pages are written first and the index last, so the index never points to a
    page that is not there yet. Pages left over from a previous, larger run are
    deleted afterwards.

    Args:
        root: Output directory. Defaults to ``settings.SITEMAP_ROOT``.
        protocol: Protocol of the URLs in the sitemaps.
        log: Optional callable that receives one line per file written.

    Returns:
        dict: ``{section: (items, pages)}``.
    """
    root = Path(root or settings.SITEMAP_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    site = Site.objects.get_current()
    base_url = f"{protocol}://{site.domain}/"

    index, written, summary = [], {INDEX_FILENAME}, {}
    for section, sitemap in get_sitemaps().items():
        pages = sitemap.paginator.num_pages
        for page in range(1, pages + 1):
            urls = sitemap.get_urls(page=page, site=site, protocol=protocol)
            filename = page_filename(section, page)
            _write(root / filename, render_to_string("sitemap.xml", {"urlset": urls}))
            written.add(filename)
            lastmods = [u["lastmod"] for u in urls if u.get("lastmod")]
            index.append(
                {
                    "location": base_url + filename,
                    "last_mod": max(lastmods) if lastmods else None,
                }
            )
            if log:
                log(f"{filename}: {len(urls)} URLs")
        summary[section] = (sitemap.paginator.count, pages)

    _write(
        root / INDEX_FILENAME,
        render_to_string("sitemap_index.xml", {"sitemaps": index}),
    )
    for path in root.iterdir():
        if PAGE_RE.match(path.name) and path.name not in written:
            path.unlink()
            if log:
                log(f"{path.name}: deleted (no longer generated)")
    return summary


def sitemap_file_view(request, filename):
    """Serve a generated sitemap file. Production nginx serves them directly."""
    path = Path(settings.SITEMAP_ROOT) / filename
    if not re.fullmatch(FILENAME_RE, filename) or not path.is_file():
        raise Http404("Sitemap not generated yet")
    response = FileResponse(path.open("rb"), content_type="application/xml")
    response["Last-Modified"] = http_date(path.stat().st_mtime)
    # Same header as django.contrib.sitemaps views: the XML itself should not
    # show up in search results.
    response["X-Robots-Tag"] = "noindex, noodp, noarchive"
    return response
