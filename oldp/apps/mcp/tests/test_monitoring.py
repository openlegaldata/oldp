"""Unit tests for the MCP monitoring/logging decorator."""

import logging
from types import SimpleNamespace

from django.test import TestCase

from oldp.apps.mcp.monitoring import (
    _summarise_result,
    _summarise_value,
    get_auth_state,
    log_tool_call,
)


class AuthStateTests(TestCase):
    """Tests for get_auth_state()."""

    def test_anon_for_none_request(self):
        self.assertEqual(get_auth_state(None), "anon")

    def test_anon_for_empty_namespace(self):
        self.assertEqual(get_auth_state(SimpleNamespace()), "anon")

    def test_anon_for_unauthenticated_user(self):
        request = SimpleNamespace(
            user=SimpleNamespace(is_authenticated=False), auth=None
        )
        self.assertEqual(get_auth_state(request), "anon")

    def test_user_pk_for_authenticated_user(self):
        request = SimpleNamespace(
            user=SimpleNamespace(is_authenticated=True, pk=42), auth=None
        )
        self.assertEqual(get_auth_state(request), "user:42")

    def test_oauth_client_id_takes_precedence(self):
        """OAuth tokens carry a linked Application with client_id."""
        auth = SimpleNamespace(application=SimpleNamespace(client_id="abc-123"))
        request = SimpleNamespace(
            user=SimpleNamespace(is_authenticated=True, pk=42), auth=auth
        )
        self.assertEqual(get_auth_state(request), "oauth:abc-123")


class SummariseValueTests(TestCase):
    """Tests for argument value summarisation used in log output."""

    def test_none(self):
        self.assertEqual(_summarise_value(None), "None")

    def test_int(self):
        self.assertEqual(_summarise_value(7), "7")

    def test_short_string(self):
        self.assertEqual(_summarise_value("hello"), "'hello'")

    def test_long_string_truncated(self):
        long_str = "x" * 500
        result = _summarise_value(long_str)
        self.assertTrue(result.startswith("<str len=500>"))

    def test_list_summary(self):
        self.assertEqual(_summarise_value([1, 2, 3]), "<list len=3>")

    def test_dict_summary(self):
        self.assertEqual(_summarise_value({"a": 1, "b": 2}), "<dict keys=2>")


class SummariseResultTests(TestCase):
    """Tests for result summarisation used in log output."""

    def test_error_result(self):
        summary = _summarise_result({"error": "Case not found."})
        self.assertIn("error=", summary)

    def test_result_with_total_and_results(self):
        summary = _summarise_result({"total": 100, "results": [{"id": 1}, {"id": 2}]})
        self.assertIn("total=100", summary)
        self.assertIn("results=2", summary)

    def test_result_with_found(self):
        summary = _summarise_result({"found": True, "matches": []})
        self.assertIn("found=True", summary)

    def test_list_result(self):
        summary = _summarise_result([1, 2, 3, 4])
        self.assertEqual(summary, "list len=4")


class LogToolCallTests(TestCase):
    """Tests for the @log_tool_call decorator."""

    def setUp(self):
        self.logger_name = "oldp.mcp.tools"

    def _make_instance(self, request=None):
        """Build a minimal fake toolset instance with a ``request`` attr."""
        return SimpleNamespace(request=request)

    def test_returns_wrapped_result(self):
        @log_tool_call
        def my_tool(self, x: int) -> dict:
            return {"result": x * 2}

        instance = self._make_instance()
        with self.assertLogs(self.logger_name, level="INFO"):
            result = my_tool(instance, 21)

        self.assertEqual(result, {"result": 42})

    def test_logs_start_and_end(self):
        @log_tool_call
        def my_tool(self) -> dict:
            return {"ok": True}

        instance = self._make_instance()
        with self.assertLogs(self.logger_name, level="INFO") as cm:
            my_tool(instance)

        joined = "\n".join(cm.output)
        self.assertIn("mcp_tool_start", joined)
        self.assertIn("mcp_tool_end", joined)
        self.assertIn("tool=my_tool", joined)

    def test_logs_include_auth_state_anon(self):
        @log_tool_call
        def my_tool(self) -> dict:
            return {}

        instance = self._make_instance(request=None)
        with self.assertLogs(self.logger_name, level="INFO") as cm:
            my_tool(instance)
        self.assertTrue(any("auth=anon" in line for line in cm.output))

    def test_logs_include_auth_state_user(self):
        @log_tool_call
        def my_tool(self) -> dict:
            return {}

        request = SimpleNamespace(
            user=SimpleNamespace(is_authenticated=True, pk=7), auth=None
        )
        instance = self._make_instance(request=request)
        with self.assertLogs(self.logger_name, level="INFO") as cm:
            my_tool(instance)
        self.assertTrue(any("auth=user:7" in line for line in cm.output))

    def test_logs_duration(self):
        @log_tool_call
        def my_tool(self) -> dict:
            return {}

        instance = self._make_instance()
        with self.assertLogs(self.logger_name, level="INFO") as cm:
            my_tool(instance)
        self.assertTrue(any("duration_ms=" in line for line in cm.output))

    def test_logs_exception_and_reraises(self):
        class Boom(RuntimeError):
            pass

        @log_tool_call
        def bad_tool(self):
            raise Boom("kapow")

        instance = self._make_instance()
        with self.assertLogs(self.logger_name, level="ERROR") as cm:
            with self.assertRaises(Boom):
                bad_tool(instance)

        joined = "\n".join(cm.output)
        self.assertIn("mcp_tool_error", joined)
        self.assertIn("tool=bad_tool", joined)
        self.assertIn("Boom", joined)

    def test_logs_kwargs(self):
        @log_tool_call
        def my_tool(self, case_id: int = 0, slug: str = "") -> dict:
            return {}

        instance = self._make_instance()
        with self.assertLogs(self.logger_name, level="INFO") as cm:
            my_tool(instance, case_id=99, slug="abc")

        joined = "\n".join(cm.output)
        self.assertIn("case_id=99", joined)
        self.assertIn("slug='abc'", joined)

    def test_preserves_function_metadata(self):
        @log_tool_call
        def my_tool(self, x: int) -> dict:
            """My docstring."""
            return {"x": x}

        self.assertEqual(my_tool.__name__, "my_tool")
        self.assertIn("docstring", my_tool.__doc__)

    def test_logger_disabled_does_not_crash(self):
        """Decorator must still work when logging is disabled upstream."""
        root_logger = logging.getLogger(self.logger_name)
        previous_level = root_logger.level
        root_logger.setLevel(logging.CRITICAL)
        try:

            @log_tool_call
            def my_tool(self) -> dict:
                return {"ok": True}

            instance = self._make_instance()
            # Should not raise even without any handlers/output
            result = my_tool(instance)
            self.assertEqual(result, {"ok": True})
        finally:
            root_logger.setLevel(previous_level)

    def test_mocked_time_measures_duration(self):
        """Verify duration measurement by patching time.perf_counter."""
        import oldp.apps.mcp.monitoring as mon

        original = mon.time.perf_counter
        counter = [0.0]

        def fake_counter():
            counter[0] += 0.5  # 500ms per call
            return counter[0]

        mon.time.perf_counter = fake_counter
        try:

            @log_tool_call
            def my_tool(self) -> dict:
                return {}

            instance = self._make_instance()
            with self.assertLogs(self.logger_name, level="INFO") as cm:
                my_tool(instance)
            self.assertTrue(any("duration_ms=500.0" in line for line in cm.output))
        finally:
            mon.time.perf_counter = original


class ThrottleLoggingTests(TestCase):
    """Ensure throttle failures are logged."""

    def test_anon_throttle_logs_on_failure(self):
        from oldp.apps.mcp.throttles import MCPAnonThrottle

        throttle = MCPAnonThrottle()
        throttle.num_requests = 1
        throttle.duration = 60
        throttle.history = [1]
        throttle.now = 0.0
        throttle.key = "test"

        with self.assertLogs("oldp.mcp.throttle", level="WARNING") as cm:
            try:
                throttle.throttle_failure()
            except Exception:
                pass
        self.assertTrue(any("mcp_throttle_hit" in line for line in cm.output))

    def test_user_throttle_logs_on_failure(self):
        from oldp.apps.mcp.throttles import MCPUserThrottle

        throttle = MCPUserThrottle()
        throttle.num_requests = 1
        throttle.duration = 60
        throttle.history = [1]
        throttle.now = 0.0
        throttle.key = "test"

        with self.assertLogs("oldp.mcp.throttle", level="WARNING") as cm:
            try:
                throttle.throttle_failure()
            except Exception:
                pass
        self.assertTrue(any("mcp_throttle_hit" in line for line in cm.output))


class AnthropicIPCachingTests(TestCase):
    """Verify that the Anthropic IP check is memoised for perf."""

    def test_lru_cache_reuses_results(self):
        from oldp.apps.mcp.throttles import _is_anthropic_ip

        # Clear cache first so we get a clean info snapshot
        _is_anthropic_ip.cache_clear()

        _is_anthropic_ip("160.79.104.10")
        _is_anthropic_ip("160.79.104.10")
        _is_anthropic_ip("160.79.104.10")

        info = _is_anthropic_ip.cache_info()
        self.assertEqual(info.hits, 2)
        self.assertEqual(info.misses, 1)
