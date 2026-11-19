"""Oracle adapter. Queries run through SQLcl using a saved connection or wallet alias.

This module never sees a password. If SQLcl needs one, the run fails and the
operator is told to stop and let the project lead connect.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from ..common.config import require
from .base import Adapter, QueryFailed
from .guard import assert_read_only, identifier

_ERR = re.compile(r"\b(ORA-\d{5}|SP2-\d{4}|SQLcl-\d+|PLS-\d{5})\b")


class OracleAdapter(Adapter):
    engine = "oracle"

    def _via_bridge(self) -> bool:
        return (self.entry.get("connection") or {}).get("transport") == "bridge"

    def _schema(self) -> str:
        if self._via_bridge():
            return "{SCHEMA}"  # filled in by the bridge; the schema name stays on that machine
        return identifier(require(self.entry.get("schema"), "database schema"), "schema").upper()

    def _connect_args(self) -> list[str]:
        """SQLcl logon arguments. Never contains a password.

        SQLcl 25.1 documentation confirms -S and -L but does not document how
        to name a saved connection at launch, so the two default forms below
        are unverified until `python -m src.db.smoke --db <id>` passes on the
        database machine. If neither works there, set connection.sqlcl_logon
        in the registry to the exact logon arguments that do (DECISIONS.md D007).
        """
        conn = self.entry.get("connection") or {}
        override = conn.get("sqlcl_logon")
        if override:
            if re.search(r"[^/\s@]+/[^@\s]+", override):
                raise QueryFailed("connection.sqlcl_logon looks like user/password; credentials are never stored")
            if not re.match(r"^[A-Za-z0-9_.\-/@ ]+$", override):
                raise QueryFailed("connection.sqlcl_logon contains unexpected characters")
            return override.split()
        mode = require(conn.get("mode"), "connection.mode (saved | wallet)")
        alias = require(conn.get("alias"), "connection.alias")
        if not re.match(r"^[A-Za-z0-9_.\-]+$", alias):
            raise QueryFailed("connection alias contains unexpected characters")
        if mode == "saved":
            return ["-name", alias]
        if mode == "wallet":
            return [f"/@{alias}"]
        raise QueryFailed(f"connection.mode must be 'saved' or 'wallet', not {mode!r}")

    def dictionary_queries(self) -> dict[str, list[str]]:
        s = self._schema()
        own = f"owner = '{s}'"
        return {
            # Row counts and block counts are optimizer statistics, not live counts.
            "tables": [f"""
                SELECT table_name, num_rows, blocks, avg_row_len, partitioned, temporary,
                       TO_CHAR(last_analyzed, 'YYYY-MM-DD') AS last_analyzed, sample_size
                FROM all_tables WHERE {own}"""],
            # low_value, high_value and histograms are deliberately not selected:
            # they hold real data values.
            # The threshold 10 below is the small-cell rule: when fewer than 10 rows are
            # non-null, the null count is withheld so it cannot be subtracted back.
            "columns": [f"""
                SELECT c.table_name, c.column_id, c.column_name, c.data_type, c.data_length,
                       c.data_precision, c.data_scale, c.nullable, c.num_distinct,
                       CASE WHEN t.num_rows - c.num_nulls < 10 THEN NULL ELSE c.num_nulls END AS num_nulls,
                       CASE WHEN t.num_rows >= 10 AND t.num_rows - c.num_nulls < 10
                            THEN 'Y' ELSE 'N' END AS nearly_all_null,
                       TO_CHAR(c.last_analyzed, 'YYYY-MM-DD') AS last_analyzed
                FROM all_tab_columns c
                LEFT JOIN all_tables t ON t.owner = c.owner AND t.table_name = c.table_name
                WHERE c.owner = '{s}'"""],
            # Oracle has no ALL_SEGMENTS. Try DBA_SEGMENTS, then USER_SEGMENTS
            # (valid only when connected as the schema owner).
            "segments": [
                f"""SELECT segment_name AS table_name, SUM(bytes) AS bytes, COUNT(*) AS segments
                    FROM dba_segments
                    WHERE {own} AND segment_type IN ('TABLE', 'TABLE PARTITION', 'TABLE SUBPARTITION')
                    GROUP BY segment_name""",
                f"""SELECT segment_name AS table_name, SUM(bytes) AS bytes, COUNT(*) AS segments
                    FROM user_segments
                    WHERE segment_type IN ('TABLE', 'TABLE PARTITION', 'TABLE SUBPARTITION')
                      AND SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') = '{s}'
                      AND SYS_CONTEXT('USERENV', 'SESSION_USER') = '{s}'
                    GROUP BY segment_name""",
            ],
            "part_tables": [f"""
                SELECT table_name, partitioning_type, subpartitioning_type, partition_count, interval
                FROM all_part_tables WHERE {own}"""],
            "part_keys": [f"""
                SELECT name AS table_name, column_name, column_position
                FROM all_part_key_columns WHERE {own} AND object_type = 'TABLE'"""],
            "constraints": [f"""
                SELECT constraint_name, constraint_type, table_name, r_owner, r_constraint_name,
                       status, validated
                FROM all_constraints WHERE {own} AND constraint_type IN ('P', 'U', 'R')"""],
            "cons_columns": [f"""
                SELECT constraint_name, table_name, column_name, position
                FROM all_cons_columns WHERE {own}"""],
            "indexes": [f"""
                SELECT index_name, table_name, uniqueness, index_type, partitioned, status
                FROM all_indexes WHERE table_owner = '{s}'"""],
            "ind_columns": [f"""
                SELECT index_name, table_name, column_name, column_position
                FROM all_ind_columns WHERE table_owner = '{s}'"""],
            "tab_comments": [f"""
                SELECT table_name, table_type, comments FROM all_tab_comments WHERE {own}"""],
            "col_comments": [f"""
                SELECT table_name, column_name, comments FROM all_col_comments
                WHERE {own} AND comments IS NOT NULL"""],
        }

    def run_to_csv(self, sql: str, out_path: Path, timeout_s: int = 600) -> None:
        body = assert_read_only(sql)
        out_path = Path(out_path).resolve()
        if self._via_bridge():
            from ..bridge import client
            opts = dict(self.entry.get("bridge_client_options") or {})
            if "repo" in opts:
                opts["repo"] = Path(opts["repo"])
            _, text = client.query(body, "dictionary", db=str(self.entry.get("id", "")),
                                   count_columns=("NUM_ROWS", "NUM_NULLS", "SAMPLE_SIZE"),
                                   purpose="dictionary audit", timeout_s=min(timeout_s, 600),
                                   **opts)
            out_path.write_text(text, encoding="utf-8")
            return
        if '"' in str(out_path):
            raise QueryFailed("output path must not contain a double quote")
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "query.sql"
            script.write_text(
                "WHENEVER SQLERROR EXIT FAILURE\n"
                "WHENEVER OSERROR EXIT FAILURE\n"
                "SET TERMOUT OFF\nSET FEEDBACK OFF\nSET ECHO OFF\nSET VERIFY OFF\n"
                "SET SQLFORMAT csv\n"
                f'SPOOL "{out_path}"\n{body};\nSPOOL OFF\nEXIT\n',
                encoding="utf-8",
            )
            cmd = ["sql", "-S", "-L", *self._connect_args(), f"@{script}"]
            try:
                # stdin is closed so a password prompt fails instead of hanging.
                proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True,
                                      text=True, timeout=timeout_s)
            except FileNotFoundError as exc:
                raise QueryFailed("SQLcl ('sql') is not on PATH on this machine") from exc
            except subprocess.TimeoutExpired as exc:
                raise QueryFailed(f"query exceeded {timeout_s}s and was stopped") from exc
        # Only error codes are surfaced; stdout/stderr text is never logged
        # because it could carry row content.
        codes = sorted(set(_ERR.findall((proc.stdout or "") + (proc.stderr or ""))))
        if proc.returncode != 0 or codes or not out_path.exists():
            out_path.unlink(missing_ok=True)
            raise QueryFailed(
                f"SQLcl failed (exit {proc.returncode}; codes: {', '.join(codes) or 'none reported'}). "
                "If SQLcl is asking for a password, stop and let the project lead connect; "
                "this tool never handles credentials."
            )
