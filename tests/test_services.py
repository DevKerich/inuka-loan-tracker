"""Business rules tested directly against the service layer (no HTTP)."""
import threading
from datetime import date

import pytest

from app import services
from app.db import connect
from app.errors import BusinessRuleError, DuplicateError, NotFoundError

TODAY = date(2026, 11, 2)


def balance(conn, ref):
    return services.get_loan_summary(conn, ref)["outstanding_balance"]


def repayment_count(conn, ref):
    return len(services.list_repayments(conn, ref)["repayments"])


# ---------- The three required scenarios ----------

def test_scenario_1_partial_payment_reduces_balance_from_10000_to_7000(conn, make_loan):
    ref = make_loan(total_due=10_000)
    assert balance(conn, ref) == 10_000

    result = services.record_repayment(conn, ref, 3_000, "PAY-001", TODAY)

    assert result["loan"]["outstanding_balance"] == 7_000
    assert result["loan"]["total_repaid"] == 3_000
    assert balance(conn, ref) == 7_000


def test_scenario_2_same_payment_reference_twice_is_recorded_only_once(conn, make_loan):
    ref = make_loan(total_due=10_000)
    services.record_repayment(conn, ref, 3_000, "PAY-DUP", TODAY)

    with pytest.raises(DuplicateError):
        services.record_repayment(conn, ref, 3_000, "PAY-DUP", TODAY)

    assert repayment_count(conn, ref) == 1
    assert balance(conn, ref) == 7_000


def test_scenario_3_overpayment_is_rejected_and_balance_is_unchanged(conn, make_loan):
    ref = make_loan(total_due=10_000, already_repaid=9_000)  # KES 1,000 outstanding
    assert balance(conn, ref) == 1_000

    with pytest.raises(BusinessRuleError, match="exceeds the outstanding balance"):
        services.record_repayment(conn, ref, 1_500, "PAY-OVER", TODAY)

    assert balance(conn, ref) == 1_000
    assert repayment_count(conn, ref) == 1  # only the setup payment


# ---------- Other rules and edge cases ----------

@pytest.mark.parametrize("amount", [0, -500])
def test_zero_or_negative_repayment_is_rejected(conn, make_loan, amount):
    ref = make_loan(total_due=5_000)

    with pytest.raises(BusinessRuleError, match="greater than zero"):
        services.record_repayment(conn, ref, amount, "PAY-BAD", TODAY)

    assert balance(conn, ref) == 5_000
    assert repayment_count(conn, ref) == 0


def test_repayment_against_missing_loan_is_rejected(conn):
    with pytest.raises(NotFoundError):
        services.record_repayment(conn, "LN-DOESNOTEXIST", 1_000, "PAY-404", TODAY)

    total = conn.execute("SELECT COUNT(*) FROM repayments").fetchone()[0]
    assert total == 0


def test_paying_exact_outstanding_balance_clears_loan_to_zero(conn, make_loan):
    ref = make_loan(total_due=4_000, already_repaid=1_000)

    services.record_repayment(conn, ref, 3_000, "PAY-FINAL", TODAY)
    assert balance(conn, ref) == 0

    # A fully paid loan accepts no further payments.
    with pytest.raises(BusinessRuleError):
        services.record_repayment(conn, ref, 1, "PAY-EXTRA", TODAY)


def test_payment_reference_is_unique_across_different_loans(conn, make_loan):
    first = make_loan(total_due=5_000)
    second = make_loan(total_due=5_000)
    services.record_repayment(conn, first, 1_000, "PAY-SHARED", TODAY)

    with pytest.raises(DuplicateError):
        services.record_repayment(conn, second, 1_000, "PAY-SHARED", TODAY)

    assert balance(conn, second) == 5_000


def test_payment_reference_check_ignores_case_and_spaces(conn, make_loan):
    ref = make_loan(total_due=5_000)
    services.record_repayment(conn, ref, 1_000, "tka1qx7b2m", TODAY)

    with pytest.raises(DuplicateError):
        services.record_repayment(conn, ref, 1_000, "  TKA1QX7B2M ", TODAY)


def test_database_unique_constraint_blocks_duplicates_even_without_app_check(conn, make_loan):
    """Second layer of defence: bypass the service and insert directly."""
    import sqlite3

    ref = make_loan(total_due=5_000)
    services.record_repayment(conn, ref, 1_000, "PAY-RAW", TODAY)
    loan_id = conn.execute("SELECT id FROM loans WHERE reference = ?", (ref,)).fetchone()[0]

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO repayments (loan_id, amount, payment_reference, payment_date) "
            "VALUES (?, 1000, 'PAY-RAW', '2026-11-02')",
            (loan_id,),
        )


def test_concurrent_payments_cannot_overpay(db_path, conn, make_loan):
    """Two payments of 600 race against a 1,000 balance: exactly one must win."""
    ref = make_loan(total_due=1_000)
    barrier = threading.Barrier(2)
    outcomes = []

    def pay(payment_reference):
        own_conn = connect(db_path)  # each "cashier" has their own connection
        barrier.wait()  # start both at the same moment
        try:
            services.record_repayment(own_conn, ref, 600, payment_reference, TODAY)
            outcomes.append("ok")
        except BusinessRuleError:
            outcomes.append("rejected")
        finally:
            own_conn.close()

    threads = [threading.Thread(target=pay, args=(f"PAY-RACE-{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(outcomes) == ["ok", "rejected"]
    assert balance(conn, ref) == 400


def test_loan_for_unknown_client_is_rejected(conn):
    with pytest.raises(NotFoundError):
        services.create_loan(conn, "CL-9999", 1_000, 1_100)


def test_duplicate_client_number_is_rejected(conn):
    services.create_client(conn, "CL-5001", "Akinyi Atieno")
    with pytest.raises(DuplicateError):
        services.create_client(conn, "CL-5001", "Someone Else")


# ---------- Regression tests from code review ----------

def test_blank_payment_reference_is_rejected(conn, make_loan):
    ref = make_loan(total_due=5_000)

    with pytest.raises(BusinessRuleError, match="Payment reference is required"):
        services.record_repayment(conn, ref, 1_000, "   ", TODAY)

    assert repayment_count(conn, ref) == 0


def test_blank_client_number_is_rejected(conn):
    with pytest.raises(BusinessRuleError):
        services.create_client(conn, "   ", "Wafula Simiyu")


def test_total_due_above_maximum_is_rejected(conn):
    services.create_client(conn, "CL-6001", "Jepkosgei Chelimo")
    with pytest.raises(BusinessRuleError, match="cannot exceed"):
        services.create_loan(conn, "CL-6001", 1, services.MAX_AMOUNT_KES + 1)
