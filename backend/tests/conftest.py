import sqlite3

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    """隔離測試用 DB 與上傳目錄，強制 DEMO_MODE 並略過 extract 延遲。"""
    db_path = tmp_path / "test.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    monkeypatch.setattr(main, "DB_PATH", db_path)
    monkeypatch.setattr(main, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(main, "DEMO_MODE", True)
    monkeypatch.setattr(main.time, "sleep", lambda _: None)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                file_name TEXT,
                file_sha256 TEXT,
                extraction_raw TEXT,
                confirmed_fields TEXT,
                edited_fields TEXT,
                factor_snapshot TEXT,
                kwh REAL,
                emission_kgco2e REAL,
                status TEXT DEFAULT 'confirmed'
            )"""
        )

    yield TestClient(main.app)
