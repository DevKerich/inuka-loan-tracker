import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DB_PATH = os.environ.get("LOAN_DB_PATH", "loans.db")


def connect(db_path=DB_PATH) -> sqlite3.Connection:
    # isolation_level=None: Python does not open transactions for us;
    # we open them explicitly with write_transaction() below.
    # check_same_thread=False: FastAPI may run the dependency and the route
    # in different worker threads; each request still uses its own connection.
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False, timeout=5)
    conn.row_factory = sqlite3.Row  # rows behave like dicts: row["amount"]
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite has FKs off by default
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())


@contextmanager
def write_transaction(conn: sqlite3.Connection):
    """Run a block as one all-or-nothing transaction.

    BEGIN IMMEDIATE takes SQLite's write lock *before* we read anything,
    so no other writer can change the balance between our check and our insert.
    Any exception rolls back every change made inside the block.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def get_db():
    """FastAPI dependency: one connection per request, always closed."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
