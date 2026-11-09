"""Generate ``server.json`` for the official MCP Registry.

Country-specific metadata (registry name, title, description) comes from the
``MCP_REGISTRY_*`` settings, which country themes such as oldp-de set; the
version is the installed OLDP version and the remote URL is
``SITE_URL`` + ``/mcp``. Publish the result with ``mcp-publisher``::

    export DJANGO_SETTINGS_MODULE=oldp_de.settings
    export DJANGO_CONFIGURATION=ProdDEConfiguration
    ./manage.py mcp_server_json --output server.json
    mcp-publisher publish server.json

See docs/mcp.md ("Official MCP Registry").
"""

import json
import re
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

import oldp

SCHEMA_URL = (
    "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
)
REPOSITORY_URL = "https://github.com/openlegaldata/oldp"

# Limits from the registry schema (ServerDetail).
_NAME_RE = re.compile(r"^[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+$")
_NAME_MAX_LENGTH = 200
_TEXT_MAX_LENGTH = 100
_VERSION_SUFFIX_RE = re.compile(r"^[0-9A-Za-z.-]+$")


def build_server_json(site_url: str, version_suffix: str = "") -> dict:
    """Build the registry ``server.json`` document from settings.

    Args:
        site_url: Public base URL of the deployment (``https://...``).
        version_suffix: Optional suffix appended as ``<version>-<suffix>``,
            for republishing changed metadata without a new OLDP release
            (the registry accepts each version only once).

    Returns:
        The ``server.json`` content as a dict.

    Raises:
        CommandError: If settings are missing or violate registry limits.
    """
    name = (getattr(settings, "MCP_REGISTRY_NAME", "") or "").strip()
    title = (getattr(settings, "MCP_REGISTRY_TITLE", "") or "").strip()
    description = (getattr(settings, "MCP_REGISTRY_DESCRIPTION", "") or "").strip()

    errors = []
    if not name:
        errors.append("MCP_REGISTRY_NAME is not set (e.g. 'io.openlegaldata/de').")
    elif not _NAME_RE.match(name) or len(name) > _NAME_MAX_LENGTH:
        errors.append(
            f"MCP_REGISTRY_NAME {name!r} must look like 'reverse.domain/server'."
        )
    if not title:
        errors.append("MCP_REGISTRY_TITLE is not set.")
    elif len(title) > _TEXT_MAX_LENGTH:
        errors.append(f"MCP_REGISTRY_TITLE is longer than {_TEXT_MAX_LENGTH} chars.")
    if not description:
        errors.append("MCP_REGISTRY_DESCRIPTION is not set.")
    elif len(description) > _TEXT_MAX_LENGTH:
        errors.append(
            f"MCP_REGISTRY_DESCRIPTION is {len(description)} chars, "
            f"max. {_TEXT_MAX_LENGTH}."
        )

    parsed = urlparse((site_url or "").strip())
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append(
            f"Site URL {site_url!r} must be a public https:// URL "
            "(set DJANGO_SITE_URL or pass --site-url)."
        )
    if version_suffix and not _VERSION_SUFFIX_RE.match(version_suffix):
        errors.append("--version-suffix may only contain [0-9A-Za-z.-].")
    if errors:
        raise CommandError("\n".join(errors))

    base_url = f"{parsed.scheme}://{parsed.netloc}"
    static_url = settings.STATIC_URL
    if not static_url.startswith(("http://", "https://")):
        static_url = base_url + "/" + static_url.lstrip("/")
    static_url = static_url.rstrip("/")
    version = oldp.__version__ + (f"-{version_suffix}" if version_suffix else "")

    return {
        "$schema": SCHEMA_URL,
        "name": name,
        "title": title,
        "description": description,
        "version": version,
        "websiteUrl": f"{base_url}/",
        "repository": {"url": REPOSITORY_URL, "source": "github"},
        # Unhashed static paths: hashed (manifest) names change every release.
        "icons": [
            {"src": f"{static_url}/images/logo.svg", "mimeType": "image/svg+xml"},
            {"src": f"{static_url}/images/logo.png", "mimeType": "image/png"},
        ],
        "remotes": [{"type": "streamable-http", "url": f"{base_url}/mcp"}],
    }


class Command(BaseCommand):
    help = "Generate server.json for the official MCP Registry from settings."

    # Pure settings rendering: no database or search backend needed.
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            "-o",
            default="-",
            help="File to write (default: stdout).",
        )
        parser.add_argument(
            "--site-url",
            default=None,
            help="Public base URL of the deployment (default: SITE_URL setting).",
        )
        parser.add_argument(
            "--version-suffix",
            default="",
            help=(
                "Append '-<suffix>' to the version, to republish changed "
                "metadata without a new OLDP release (e.g. '1')."
            ),
        )

    def handle(self, *args, **options):
        site_url = options["site_url"] or getattr(settings, "SITE_URL", "")
        data = build_server_json(site_url, options["version_suffix"])
        content = json.dumps(data, indent=2, ensure_ascii=False) + "\n"

        if options["output"] == "-":
            self.stdout.write(content, ending="")
        else:
            with open(options["output"], "w", encoding="utf-8") as f:
                f.write(content)
            self.stderr.write(
                f"Wrote {options['output']} ({data['name']} {data['version']})"
            )
