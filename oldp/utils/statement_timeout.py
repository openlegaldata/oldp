"""Per-statement execution time limit for read queries (MariaDB).

gunicorn kills a worker that runs past its ``--timeout`` and nginx then
answers 504. The killed worker's SQL keeps running on the database until
it finishes, so a slow query also ties up the DB for as long as it runs.
:func:`statement_timeout` lets MariaDB abort a ``SELECT`` itself, which
raises an error inside the request in time to return a useful answer.
"""

import logging
from contextlib import contextmanager

from django.db import OperationalError, connection

logger = logging.getLogger(__name__)

# ER_STATEMENT_TIMEOUT: "Query execution was interrupted
# (max_statement_time exceeded)".
MARIADB_STATEMENT_TIMEOUT_ERRNO = 1969


def _supports_statement_timeout() -> bool:
    return connection.vendor == "mysql" and connection.mysql_is_mariadb


@contextmanager
def statement_timeout(seconds: float):
    """Abort every ``SELECT`` in the block that runs longer than ``seconds``.

    Prefixes each ``SELECT`` with MariaDB's ``SET STATEMENT
    max_statement_time=<seconds> FOR``. The limit applies to that statement
    only, so pooled connections keep their session settings. Other
    statements and other database backends (SQLite in tests, MySQL) run
    unchanged. A non-positive ``seconds`` disables the limit.

    A statement that runs out of time raises ``OperationalError``. Check it
    with :func:`is_statement_timeout`.

    Args:
        seconds: Limit per statement, in seconds.
    """
    if not seconds or seconds <= 0 or not _supports_statement_timeout():
        yield
        return

    prefix = f"SET STATEMENT max_statement_time={float(seconds):g} FOR "

    def wrapper(execute, sql, params, many, context):
        if sql.lstrip()[:6].upper() == "SELECT":
            sql = prefix + sql
        return execute(sql, params, many, context)

    with connection.execute_wrapper(wrapper):
        yield


def is_statement_timeout(exc: BaseException) -> bool:
    """True if ``exc`` is MariaDB aborting a statement under its time limit."""
    return (
        isinstance(exc, OperationalError)
        and bool(exc.args)
        and exc.args[0] == MARIADB_STATEMENT_TIMEOUT_ERRNO
    )
