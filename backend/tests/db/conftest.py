"""Shared fixtures for db tests.

Every test gets a fresh, temp-file SQLite database. We point the db module at it
via the `FINALLY_DB_PATH` env var and reset the cached path between tests so the
real `db/finally.db` is never touched.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.db.connection import reset_db_path_cache


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the db module at a fresh temp file for this test."""
    path = tmp_path / "test_finally.db"
    monkeypatch.setenv("FINALLY_DB_PATH", str(path))
    reset_db_path_cache()
    yield path
    reset_db_path_cache()


@pytest.fixture
def fresh_db(db_path: Path):
    """Open a connection, triggering lazy init. Closes after test."""
    from app.db import get_db
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch):
    """Ensure no stray FINALLY_DB_PATH leaks between tests when db_path fixture isn't used."""
    if "FINALLY_DB_PATH" in os.environ and "PYTEST_CURRENT_TEST" not in os.environ:
        monkeypatch.delenv("FINALLY_DB_PATH", raising=False)
