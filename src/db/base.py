"""Engine adapter interface. Audit code talks to this, never to an engine directly."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class QueryFailed(RuntimeError):
    pass


class Adapter(ABC):
    engine = "abstract"

    def __init__(self, entry: dict):
        self.entry = entry

    @abstractmethod
    def dictionary_queries(self) -> dict[str, list[str]]:
        """Map each dictionary dataset name to SQL alternatives, tried in order.

        Required names: tables, columns, segments, part_tables, part_keys,
        constraints, cons_columns, indexes, ind_columns, tab_comments, col_comments.
        Queries must read the data dictionary only: no scan of a data table,
        and no column that holds data values (for example column min/max
        statistics or histogram endpoints).
        """

    @abstractmethod
    def run_to_csv(self, sql: str, out_path: Path, timeout_s: int = 600) -> None:
        """Run one read-only query and write its result to out_path as CSV with a header.

        Row content must go to the file only, never to stdout or a log.
        Raise QueryFailed on error.
        """


class NotImplementedAdapter(Adapter):
    """Stub for engines that are registered but not yet supported."""

    def _fail(self):
        raise NotImplementedError(
            f"The {self.engine} adapter is not implemented yet. Implement "
            f"dictionary_queries() and run_to_csv() in src/db/{self.engine}.py "
            f"(see src/db/oracle.py for the contract), then rerun."
        )

    def dictionary_queries(self):
        self._fail()

    def run_to_csv(self, sql, out_path, timeout_s=600):
        self._fail()


def get_adapter(entry: dict) -> Adapter:
    engine = str(entry.get("engine", "")).lower()
    if engine == "oracle":
        from .oracle import OracleAdapter
        return OracleAdapter(entry)
    if engine == "postgresql":
        from .postgresql import PostgresqlAdapter
        return PostgresqlAdapter(entry)
    if engine == "sqlserver":
        from .sqlserver import SqlServerAdapter
        return SqlServerAdapter(entry)
    if engine == "mysql":
        from .mysql import MysqlAdapter
        return MysqlAdapter(entry)
    if engine == "fixture":
        from .fixture import FixtureAdapter
        return FixtureAdapter(entry)
    raise ValueError(f"unknown engine '{engine}' for database '{entry.get('id')}'")
