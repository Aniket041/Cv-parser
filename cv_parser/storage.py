"""Local SQLite persistence for batches and editable extraction records."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .schema import CandidateRecord, EXPORT_COLUMNS


class Storage:
    def __init__(self, db_path: str | Path = "data/cv_parser.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    name TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id INTEGER NOT NULL REFERENCES batches(id),
                    source_file TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    processing_status TEXT NOT NULL,
                    name TEXT, email TEXT, phone TEXT, total_experience_years TEXT,
                    latest_designation TEXT, latest_company TEXT, locations TEXT,
                    qualifications TEXT, qualification_years TEXT, confidence REAL,
                    review_notes TEXT, evidence_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(batch_id, file_hash)
                );
            """)

    def create_batch(self, name: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute("INSERT INTO batches(name) VALUES (?)", (name,))
            return int(cursor.lastrowid)

    def add_record(self, batch_id: int, record: CandidateRecord) -> bool:
        values = record.db_dict()
        with self._connect() as connection:
            cursor = connection.execute("""
                INSERT OR IGNORE INTO records (
                    batch_id, source_file, file_hash, processing_status, name, email, phone,
                    total_experience_years, latest_designation, latest_company, locations,
                    qualifications, qualification_years, confidence, review_notes, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (batch_id, values["source_file"], values["file_hash"], values["processing_status"], values["name"],
                  values["email"], values["phone"], values["total_experience_years"], values["latest_designation"],
                  values["latest_company"], values["locations"], values["qualifications"], values["qualification_years"],
                  values["confidence"], values["review_notes"], json.dumps(values["evidence"])))
            return cursor.rowcount == 1

    def records(self, batch_id: int) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM records WHERE batch_id = ? ORDER BY id", (batch_id,)).fetchall()
        return [dict(row) for row in rows]

    def update_records(self, records: Iterable[dict]) -> None:
        editable = [column for column in EXPORT_COLUMNS if column != "source_file"]
        with self._connect() as connection:
            for record in records:
                if "id" not in record:
                    continue
                assignments = ", ".join(f"{column} = ?" for column in editable)
                values = [record.get(column, "") for column in editable] + [record["id"]]
                connection.execute(f"UPDATE records SET {assignments} WHERE id = ?", values)

    def evidence(self, record_id: int) -> dict:
        with self._connect() as connection:
            row = connection.execute("SELECT evidence_json FROM records WHERE id = ?", (record_id,)).fetchone()
        return json.loads(row["evidence_json"]) if row else {}

