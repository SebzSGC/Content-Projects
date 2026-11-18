"""Additive storage in the orchestrator database."""
import json
import sqlite3
from contextlib import closing, contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS highlight_runs (
    id TEXT PRIMARY KEY, source TEXT NOT NULL, sha256 TEXT NOT NULL,
    mode TEXT NOT NULL, state TEXT NOT NULL, error TEXT, elapsed REAL, source_signature TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS highlight_revisions (
    seq INTEGER PRIMARY KEY, run_id TEXT, candidate TEXT NOT NULL,
    provenance TEXT NOT NULL, operation TEXT NOT NULL UNIQUE, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS highlight_revision_candidate
    ON highlight_revisions(run_id, candidate, seq);
CREATE TABLE IF NOT EXISTS highlight_profiles (
    id TEXT PRIMARY KEY, payload TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path):
        self.path = path

    @contextmanager
    def connect(self, write=False):
        with closing(sqlite3.connect(self.path, timeout=30)) as connection:
            connection.row_factory = sqlite3.Row
            with connection:
                if write:
                    connection.execute("BEGIN IMMEDIATE")
                yield connection

    def migrate(self):
        with self.connect() as db:
            db.executescript(SCHEMA)
            db.execute("UPDATE highlight_runs SET state='FAILED', error='Servidor reiniciado' WHERE state='RUNNING'")

    def run(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM highlight_runs WHERE id=?", (run_id,)).fetchone()
            return dict(row) if row else None

    def history(self, run_id, candidate=None):
        query = "SELECT * FROM highlight_revisions WHERE run_id=?"
        params = (run_id,)
        if candidate is not None:
            query += " AND candidate=?"
            params += (candidate,)
        with self.connect() as db:
            return [{**dict(row), "payload": json.loads(row["payload"])}
                    for row in db.execute(query + " ORDER BY seq", params)]

    def save_review(self, run_id, candidate, operation, expected, payload, *,
                    provenance="revision_editorial_explicita"):
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self.connect(write=True) as db:
            previous = db.execute("SELECT * FROM highlight_revisions WHERE operation=?", (operation,)).fetchone()
            if previous:
                if (previous["run_id"], previous["candidate"], previous["payload"]) != (run_id, candidate, encoded):
                    raise ValueError("La operación ya existe con otros datos")
                return previous["seq"]
            latest = db.execute("SELECT max(seq) FROM highlight_revisions WHERE run_id=? AND candidate=?",
                                (run_id, candidate)).fetchone()[0]
            if latest != expected:
                raise ValueError("La revisión cambió. Recarga el historial.")
            return db.execute(
                "INSERT INTO highlight_revisions(run_id,candidate,provenance,operation,payload) VALUES(?,?,?,?,?)",
                (run_id, candidate, provenance, operation, encoded),
            ).lastrowid
