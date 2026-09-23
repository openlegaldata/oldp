"""OAuth discovery metadata must be reachable where clients look for it.

The documents were served only at the site root. MCP clients derive the
discovery URL from the resource they are talking to and request it under
``/mcp/``, so they got 404 -- 675 of them in a 30-day window, against 13.3k
successful tool calls. A 404 there reads as "this server has no OAuth support"
to a spec-compliant client, rather than "look elsewhere".

RFC 9728 specifies a third form for resource identifiers that carry a path:
the path is appended to the well-known document. All three are served, and all
three must return the same metadata, because they describe one resource.
"""

import json

from django.test import TestCase


class WellKnownDiscoveryTestCase(TestCase):
    PROTECTED_RESOURCE_PATHS = (
        "/.well-known/oauth-protected-resource",
        "/mcp/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/mcp",
    )
    AUTH_SERVER_PATHS = (
        "/.well-known/oauth-authorization-server",
        "/mcp/.well-known/oauth-authorization-server",
        "/.well-known/oauth-authorization-server/mcp",
    )

    def test_protected_resource_metadata_served_at_every_path(self):
        for path in self.PROTECTED_RESOURCE_PATHS:
            with self.subTest(path=path):
                res = self.client.get(path)
                self.assertEqual(res.status_code, 200)
                self.assertEqual(res["Content-Type"].split(";")[0], "application/json")

    def test_authorization_server_metadata_served_at_every_path(self):
        for path in self.AUTH_SERVER_PATHS:
            with self.subTest(path=path):
                res = self.client.get(path)
                self.assertEqual(res.status_code, 200)

    def test_all_paths_return_identical_metadata(self):
        """One resource, one answer -- a client must not get different views."""
        bodies = {
            path: json.loads(self.client.get(path).content)
            for path in self.PROTECTED_RESOURCE_PATHS
        }
        first = bodies[self.PROTECTED_RESOURCE_PATHS[0]]
        for path, body in bodies.items():
            self.assertEqual(body, first, f"{path} disagrees with the root document")

    def test_metadata_names_an_authorization_server(self):
        """A document that omits this is useless to a client."""
        body = json.loads(self.client.get(self.PROTECTED_RESOURCE_PATHS[0]).content)
        self.assertTrue(
            body.get("authorization_servers") or body.get("authorization_server"),
            f"no authorization server advertised: {body}",
        )

    def test_get_on_mcp_is_declined_with_allow_header(self):
        """POST-only is deliberate; declining must still be spec-correct."""
        res = self.client.get("/mcp")
        self.assertEqual(res.status_code, 405)
        allowed = {m.strip() for m in res["Allow"].split(",")}
        self.assertIn("POST", allowed)
        self.assertNotIn("GET", allowed)
