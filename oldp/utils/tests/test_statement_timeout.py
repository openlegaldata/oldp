"""Tests for :mod:`oldp.utils.statement_timeout`."""

from unittest.mock import patch

from django.db import OperationalError, connection
from django.test import TestCase

from oldp.utils.statement_timeout import (
    MARIADB_STATEMENT_TIMEOUT_ERRNO,
    is_statement_timeout,
    statement_timeout,
)

SUPPORTS = "oldp.utils.statement_timeout._supports_statement_timeout"


class _Recorder:
    """Innermost execute wrapper: records the final SQL, skips execution."""

    def __init__(self):
        self.sql = []

    def __call__(self, execute, sql, params, many, context):
        self.sql.append(sql)
        return None


class StatementTimeoutTests(TestCase):
    def _run(self, seconds, statements, supported=True):
        recorder = _Recorder()
        with patch(SUPPORTS, return_value=supported):
            with statement_timeout(seconds), connection.execute_wrapper(recorder):
                with connection.cursor() as cursor:
                    for sql in statements:
                        cursor.execute(sql)
        return recorder.sql

    def test_prefixes_selects_only(self):
        sql = self._run(2.5, ["SELECT 1", "  select 2", "UPDATE t SET a = 1"])
        self.assertEqual(
            sql,
            [
                "SET STATEMENT max_statement_time=2.5 FOR SELECT 1",
                "SET STATEMENT max_statement_time=2.5 FOR   select 2",
                "UPDATE t SET a = 1",
            ],
        )

    def test_whole_seconds_have_no_fraction(self):
        sql = self._run(3.0, ["SELECT 1"])
        self.assertEqual(sql, ["SET STATEMENT max_statement_time=3 FOR SELECT 1"])

    def test_unsupported_backend_is_unchanged(self):
        self.assertEqual(self._run(3, ["SELECT 1"], supported=False), ["SELECT 1"])

    def test_zero_disables_limit(self):
        self.assertEqual(self._run(0, ["SELECT 1"]), ["SELECT 1"])
        self.assertEqual(self._run(-1, ["SELECT 1"]), ["SELECT 1"])

    def test_limit_ends_with_block(self):
        recorder = _Recorder()
        with patch(SUPPORTS, return_value=True):
            with statement_timeout(3):
                pass
            with connection.execute_wrapper(recorder):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
        self.assertEqual(recorder.sql, ["SELECT 1"])

    def test_is_statement_timeout(self):
        self.assertTrue(
            is_statement_timeout(
                OperationalError(MARIADB_STATEMENT_TIMEOUT_ERRNO, "interrupted")
            )
        )
        self.assertFalse(is_statement_timeout(OperationalError(2006, "gone away")))
        self.assertFalse(is_statement_timeout(OperationalError()))
        self.assertFalse(is_statement_timeout(ValueError(1969)))

    def test_mariadb_aborts_slow_select(self):
        # Checked here, not in a decorator: ``mysql_is_mariadb`` connects.
        if not (connection.vendor == "mysql" and connection.mysql_is_mariadb):
            self.skipTest("needs MariaDB")
        with self.assertRaises(OperationalError) as ctx:
            with statement_timeout(0.2):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT SLEEP(2)")
        self.assertTrue(is_statement_timeout(ctx.exception))
