"""
Tiny SQLite persistence layer.

Allows project to store finance runs instead of being single use
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict

import pandas as pd

DB_PATH = Path("fpa_runs.db")


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            assumptions_json TEXT NOT NULL
        )
        """
    )
    return conn


def save_run(run_name: str, assumptions: Dict[str, float], tables: Dict[str, pd.DataFrame]) -> int:
    """Save one analysis run and its core tables to local SQLite."""
    conn = get_connection()
    created_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO analysis_runs (run_name, created_at, assumptions_json) VALUES (?, ?, ?)",
        (run_name, created_at, json.dumps(assumptions)),
    )
    run_id = cur.lastrowid

    for table_name, df in tables.items():
        if df is None or df.empty:
            continue
        temp = df.copy()
        temp["run_id"] = run_id
        temp.to_sql(f"run_{table_name}", conn, if_exists="append", index=False)

    conn.commit()
    conn.close()
    return int(run_id)


def list_runs() -> pd.DataFrame:
    """Return saved analysis runs."""
    conn = get_connection()
    runs = pd.read_sql_query("SELECT id, run_name, created_at, assumptions_json FROM analysis_runs ORDER BY id DESC", conn)
    conn.close()
    return runs
