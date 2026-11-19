"""Static read-only check for every statement sent to a database (project rule 2).

This is a second line of defence. The first is a database account that holds
only SELECT privileges; ask the DBA to confirm that it does.
"""
from __future__ import annotations

import re

FORBIDDEN = (
    "INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT", "CREATE", "ALTER", "DROP",
    "TRUNCATE", "RENAME", "GRANT", "REVOKE", "COMMENT", "PURGE", "FLASHBACK",
    "CALL", "EXEC", "EXECUTE", "BEGIN", "DECLARE", "LOCK", "COMMIT", "ROLLBACK",
    "SAVEPOINT", "ANALYZE", "AUDIT", "NOAUDIT", "COPY", "HOST",
)
_IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,127}$")


class ReadOnlyViolation(RuntimeError):
    pass


def strip_literals(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
    return sql


def assert_read_only(sql: str) -> str:
    """Raise unless sql is a single SELECT/WITH query. Returns sql without a trailing ';'."""
    body = sql.strip().rstrip(";").strip()
    bare = strip_literals(body)
    if ";" in bare:
        raise ReadOnlyViolation("more than one statement")
    first = re.match(r"\s*\(*\s*([A-Za-z]+)", bare)
    if not first or first.group(1).upper() not in ("SELECT", "WITH"):
        raise ReadOnlyViolation("only SELECT or WITH queries are allowed")
    words = set(re.findall(r"[A-Za-z_]+", bare.upper()))
    hit = sorted(words.intersection(FORBIDDEN))
    if hit:
        raise ReadOnlyViolation(f"forbidden keyword(s): {', '.join(hit)}")
    if re.search(r"\bFOR\s+UPDATE\b", bare, flags=re.I):
        raise ReadOnlyViolation("SELECT ... FOR UPDATE takes locks")
    if re.search(r"\bINTO\b", bare, flags=re.I):
        raise ReadOnlyViolation("SELECT ... INTO is not allowed")
    return body


def identifier(name: str, what: str = "identifier") -> str:
    """Validate a schema or object name before it is placed in SQL text."""
    if not isinstance(name, str) or not _IDENT.match(name):
        raise ReadOnlyViolation(f"unsafe {what}: {name!r}")
    return name
