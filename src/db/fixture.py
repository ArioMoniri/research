"""Fixture adapter for tests: serves canned dictionary CSVs from a directory.

It holds synthetic metadata only and is never used for a real database.
"""
import shutil
from pathlib import Path

from .base import Adapter, QueryFailed
from .guard import assert_read_only

NAMES = ("tables", "columns", "segments", "part_tables", "part_keys", "constraints",
         "cons_columns", "indexes", "ind_columns", "tab_comments", "col_comments")


class FixtureAdapter(Adapter):
    engine = "fixture"

    def dictionary_queries(self):
        return {name: [f"SELECT * FROM {name}"] for name in NAMES}

    def run_to_csv(self, sql, out_path, timeout_s=600):
        name = assert_read_only(sql).split()[-1]
        src = Path(self.entry["fixture_dir"]) / f"{name}.csv"
        if not src.exists():
            raise QueryFailed(f"no fixture for {name}")
        shutil.copy(src, out_path)
