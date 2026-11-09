"""Tests for ``manage.py mcp_server_json`` (MCP Registry server.json)."""

import json
import tempfile
from io import StringIO
from pathlib import Path

import jsonschema
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings

import oldp

# Copy of the registry schema referenced by SCHEMA_URL, so the test runs offline.
_SCHEMA = json.loads(
    (Path(__file__).parent / "data" / "server.schema.2025-12-11.json").read_text()
)

_DE = {
    "MCP_REGISTRY_NAME": "io.openlegaldata/de",
    "MCP_REGISTRY_TITLE": "Open Legal Data (Germany)",
    "MCP_REGISTRY_DESCRIPTION": (
        "German court decisions (Rechtsprechung) and laws (Gesetze) with "
        "citation graph and citation checks."
    ),
    "SITE_URL": "https://de.openlegaldata.io",
    "STATIC_URL": "/static/",
}


def _run(*args):
    out = StringIO()
    call_command("mcp_server_json", *args, stdout=out, stderr=StringIO())
    return json.loads(out.getvalue())


@override_settings(**_DE)
class MCPServerJsonCommandTests(SimpleTestCase):
    def test_output_is_valid_registry_document(self):
        data = _run()
        jsonschema.validate(data, _SCHEMA, format_checker=jsonschema.FormatChecker())

    def test_values_from_settings_and_package(self):
        data = _run()
        self.assertEqual(data["name"], "io.openlegaldata/de")
        self.assertEqual(data["title"], "Open Legal Data (Germany)")
        self.assertEqual(data["version"], oldp.__version__)
        self.assertEqual(data["websiteUrl"], "https://de.openlegaldata.io/")
        self.assertEqual(
            data["remotes"],
            [{"type": "streamable-http", "url": "https://de.openlegaldata.io/mcp"}],
        )
        self.assertEqual(
            data["icons"][0]["src"],
            "https://de.openlegaldata.io/static/images/logo.svg",
        )
        self.assertEqual(
            data["repository"]["url"], "https://github.com/openlegaldata/oldp"
        )

    def test_site_url_option_overrides_setting(self):
        data = _run("--site-url", "https://at.openlegaldata.io/")
        self.assertEqual(data["remotes"][0]["url"], "https://at.openlegaldata.io/mcp")

    @override_settings(STATIC_URL="https://cdn.example.org/static/")
    def test_absolute_static_url(self):
        self.assertEqual(
            _run()["icons"][1]["src"], "https://cdn.example.org/static/images/logo.png"
        )

    def test_writes_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "server.json"
            call_command("mcp_server_json", "--output", str(path), stderr=StringIO())
            self.assertEqual(
                json.loads(path.read_text())["name"], "io.openlegaldata/de"
            )

    @override_settings(
        MCP_REGISTRY_NAME="", MCP_REGISTRY_TITLE="", MCP_REGISTRY_DESCRIPTION=""
    )
    def test_core_defaults_refuse_to_render(self):
        with self.assertRaisesMessage(CommandError, "MCP_REGISTRY_NAME is not set"):
            _run()

    def test_invalid_values_are_rejected(self):
        bad = [
            {"MCP_REGISTRY_NAME": "no-slash"},
            {"MCP_REGISTRY_TITLE": "t" * 101},
            {"MCP_REGISTRY_DESCRIPTION": "d" * 101},
            {"SITE_URL": "http://localhost:8000"},
        ]
        for overrides in bad:
            with self.subTest(**{k: v[:20] for k, v in overrides.items()}):
                with override_settings(**overrides), self.assertRaises(CommandError):
                    _run()
