from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import services
from app.db import connect, get_db, init_db
from app.main import app


@pytest.fixture
def db_path(tmp_path):
    """A brand-new SQLite file per test, deleted by pytest afterwards."""
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path):
    conn = connect(db_path)
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def make_loan(conn):
    """Create a client + loan and return the loan reference.

    Optionally pre-pay `already_repaid` so the loan starts with a chosen outstanding balance.
    """
    counter = iter(range(1, 1000))

    def _make_loan(total_due: int, already_repaid: int = 0) -> str:
        n = next(counter)
        client_number = f"CL-T{n:03d}"
        services.create_client(conn, client_number, f"Test Client {n}")
        loan = services.create_loan(conn, client_number, principal=total_due, total_due=total_due)
        if already_repaid:
            services.record_repayment(conn, loan["reference"], already_repaid, f"SETUP-{n}", date(2026, 10, 1))
        return loan["reference"]

    return _make_loan


@pytest.fixture
def api(conn):
    """HTTP client whose requests all use the isolated test database."""
    app.dependency_overrides[get_db] = lambda: conn
    # Not used as a context manager, so the app's startup hook does not touch loans.db.
    yield TestClient(app)
    app.dependency_overrides.clear()
