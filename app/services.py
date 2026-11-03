"""Business logic. No FastAPI imports here, so every rule can be tested directly.

Every function takes an open sqlite3 connection as its first argument.
Money is always an int of whole KES.
"""
import sqlite3
import uuid
from datetime import date

from app.db import write_transaction
from app.errors import BusinessRuleError, DuplicateError, NotFoundError

# KES 100 million: far above any microloan, far below SQLite's 64-bit INTEGER limit.
MAX_AMOUNT_KES = 100_000_000


# ---------- Clients ----------

def create_client(conn: sqlite3.Connection, client_number: str, name: str) -> dict:
    client_number = client_number.strip().upper()
    name = name.strip()
    if not client_number or not name:
        raise BusinessRuleError("Client number and name are required.")
    try:
        with write_transaction(conn):
            conn.execute(
                "INSERT INTO clients (client_number, name) VALUES (?, ?)",
                (client_number, name),
            )
    except sqlite3.IntegrityError:
        # The UNIQUE constraint on client_number fired.
        raise DuplicateError(f"Client number '{client_number}' is already registered.")
    return get_client(conn, client_number)


def get_client(conn: sqlite3.Connection, client_number: str) -> dict:
    row = conn.execute(
        "SELECT * FROM clients WHERE client_number = ?", (client_number.strip().upper(),)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Client '{client_number}' does not exist.")
    return dict(row)


# ---------- Loans ----------

def _new_loan_reference() -> str:
    # Random, so there is no "next number" race; the UNIQUE constraint is the backstop.
    return "LN-" + uuid.uuid4().hex[:8].upper()


def create_loan(conn: sqlite3.Connection, client_number: str, principal: int, total_due: int) -> dict:
    if principal <= 0:
        raise BusinessRuleError("Principal must be greater than zero.")
    if total_due < principal:
        raise BusinessRuleError("Total amount due cannot be less than the principal.")
    if total_due > MAX_AMOUNT_KES:
        raise BusinessRuleError(f"Total amount due cannot exceed KES {MAX_AMOUNT_KES:,}.")

    reference = _new_loan_reference()
    with write_transaction(conn):
        client = get_client(conn, client_number)  # raises NotFoundError -> rollback
        conn.execute(
            "INSERT INTO loans (reference, client_id, principal, total_due) VALUES (?, ?, ?, ?)",
            (reference, client["id"], principal, total_due),
        )
    return get_loan_summary(conn, reference)


def _get_loan_row(conn: sqlite3.Connection, loan_reference: str) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT loans.*, clients.client_number, clients.name AS client_name
        FROM loans JOIN clients ON clients.id = loans.client_id
        WHERE loans.reference = ?
        """,
        (loan_reference.strip().upper(),),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Loan '{loan_reference}' does not exist.")
    return row


def get_total_repaid(conn: sqlite3.Connection, loan_id: int) -> int:
    # COALESCE turns SUM of zero rows (NULL) into 0.
    return conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM repayments WHERE loan_id = ?", (loan_id,)
    ).fetchone()[0]


def get_outstanding_balance(conn: sqlite3.Connection, loan: sqlite3.Row) -> int:
    """THE balance calculation: total due minus everything actually recorded.

    Derived from the repayments table on every call, so it can never drift.
    """
    return loan["total_due"] - get_total_repaid(conn, loan["id"])


def _summarise(conn: sqlite3.Connection, loan: sqlite3.Row) -> dict:
    total_repaid = get_total_repaid(conn, loan["id"])
    return {
        "reference": loan["reference"],
        "client_number": loan["client_number"],
        "client_name": loan["client_name"],
        "principal": loan["principal"],
        "total_due": loan["total_due"],
        "total_repaid": total_repaid,
        "outstanding_balance": loan["total_due"] - total_repaid,
        "created_at": loan["created_at"],
    }


def get_loan_summary(conn: sqlite3.Connection, loan_reference: str) -> dict:
    return _summarise(conn, _get_loan_row(conn, loan_reference))


def list_loans(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT loans.*, clients.client_number, clients.name AS client_name
        FROM loans JOIN clients ON clients.id = loans.client_id
        ORDER BY loans.id
        """
    ).fetchall()
    return [_summarise(conn, row) for row in rows]


# ---------- Repayments ----------

def record_repayment(
    conn: sqlite3.Connection,
    loan_reference: str,
    amount: int,
    payment_reference: str,
    payment_date: date,
) -> dict:
    """Record one repayment, enforcing every business rule.

    Rule order matters:
      1. amount > 0               (no point touching the DB otherwise)
      2. loan exists              -> NotFoundError
      3. reference not used       -> DuplicateError (checked before overpayment, so
                                     re-sending a payment that cleared a loan is
                                     reported as a duplicate, not an overpayment)
      4. amount <= outstanding    -> BusinessRuleError
    Steps 2-4 and the INSERT share one locked transaction, so a rejected or
    concurrent payment can never leave the balance wrong.
    """
    if amount <= 0:
        raise BusinessRuleError("Repayment amount must be greater than zero.")
    payment_reference = payment_reference.strip().upper()
    if not payment_reference:
        raise BusinessRuleError("Payment reference is required.")

    try:
        with write_transaction(conn):
            loan = _get_loan_row(conn, loan_reference)

            already_used = conn.execute(
                "SELECT 1 FROM repayments WHERE payment_reference = ?", (payment_reference,)
            ).fetchone()
            if already_used:
                raise DuplicateError(
                    f"Payment reference '{payment_reference}' has already been recorded."
                )

            outstanding = get_outstanding_balance(conn, loan)
            if amount > outstanding:
                raise BusinessRuleError(
                    f"Repayment of KES {amount:,} exceeds the outstanding balance "
                    f"of KES {outstanding:,}."
                )

            cursor = conn.execute(
                """
                INSERT INTO repayments (loan_id, amount, payment_reference, payment_date)
                VALUES (?, ?, ?, ?)
                """,
                (loan["id"], amount, payment_reference, payment_date.isoformat()),
            )
            # Built before COMMIT, so the balance shown is exactly the one this
            # payment produced, not one including a payment that landed after it.
            repayment = conn.execute(
                "SELECT * FROM repayments WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            result = {"repayment": _repayment_dict(repayment), "loan": _summarise(conn, loan)}
    except sqlite3.IntegrityError:
        # Safety net: the UNIQUE constraint on payment_reference fired even
        # though the check above passed. The transaction was rolled back.
        raise DuplicateError(f"Payment reference '{payment_reference}' has already been recorded.")

    return result


def list_repayments(conn: sqlite3.Connection, loan_reference: str) -> dict:
    loan = _get_loan_row(conn, loan_reference)
    rows = conn.execute(
        "SELECT * FROM repayments WHERE loan_id = ? ORDER BY payment_date, id", (loan["id"],)
    ).fetchall()
    return {"loan": _summarise(conn, loan), "repayments": [_repayment_dict(r) for r in rows]}


def _repayment_dict(row: sqlite3.Row) -> dict:
    return {
        "payment_reference": row["payment_reference"],
        "amount": row["amount"],
        "payment_date": row["payment_date"],
        "recorded_at": row["created_at"],
    }
