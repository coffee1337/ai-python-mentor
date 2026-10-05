"""Worker-local durable at-most-once launch claims; no application DB credentials."""
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

class Conflict(ValueError):
    pass

class Journal:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.directory / "journal.sqlite3"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS jobs(caller TEXT, key TEXT, digest TEXT NOT NULL, state TEXT NOT NULL, response TEXT, created REAL NOT NULL, PRIMARY KEY(caller,key))")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    def claim(self, caller, key, body):
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT digest,state,response FROM jobs WHERE caller=? AND key=?", (caller, key)).fetchone()
            if row:
                db.commit()
                if row[0] != digest:
                    raise Conflict("key_body_mismatch")
                return False, json.loads(row[2]) if row[2] else None
            # Persist intent BEFORE touching the runtime. Unknown outcomes never launch again.
            db.execute("INSERT INTO jobs VALUES (?,?,?,'running',NULL,?)", (caller, key, digest, time.time()))
            db.commit()
            return True, None

    def lookup(self, caller, key, body):
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with self.connect() as db:
            row = db.execute("SELECT digest,response FROM jobs WHERE caller=? AND key=?", (caller, key)).fetchone()
            if row is None:
                return False, None
            if row[0] != digest:
                raise Conflict("key_body_mismatch")
            return True, json.loads(row[1]) if row[1] else None

    def finish(self, caller, key, response):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT response FROM jobs WHERE caller=? AND key=?", (caller, key)).fetchone()
            encoded = json.dumps(response, sort_keys=True)
            if current is None or current[0] is not None and current[0] != encoded:
                db.rollback()
                raise Conflict("terminal_result_conflict")
            db.execute("UPDATE jobs SET state='finished',response=? WHERE caller=? AND key=?", (encoded, caller, key))
            db.commit()

    def unfinished(self):
        with self.connect() as db:
            return db.execute("SELECT caller,key FROM jobs WHERE response IS NULL").fetchall()
