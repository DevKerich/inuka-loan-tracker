"""Load fictional demo data. All names, numbers and payment references are made up.

Run from the project root:  python -m scripts.seed
"""
from datetime import date

from app import services
from app.db import connect, init_db, DB_PATH

CLIENTS = [
    ("CL-1001", "Wanjiru Kamau"),
    ("CL-1002", "Otieno Ochieng"),
    ("CL-1003", "Chebet Kiprono"),
    ("CL-1004", "Mutua Musyoka"),
]

# (client_number, principal, total_due, [(amount, payment_reference, payment_date), ...])
LOANS = [
    ("CL-1001", 10_000, 11_500, [(1_500, "TKA1QX7B2M", date(2026, 9, 5))]),   # 10,000 outstanding
    ("CL-1002", 5_000, 5_750, [(2_000, "TKB4LP9C3N", date(2026, 9, 12)),
                               (2_750, "TKC8RT2D4P", date(2026, 10, 10))]),   # 1,000 outstanding
    ("CL-1003", 20_000, 23_000, []),                                          # nothing paid yet
    ("CL-1004", 3_000, 3_300, [(3_300, "TKD2WS5E6Q", date(2026, 10, 1))]),    # fully paid
]


def main():
    conn = connect()
    init_db(conn)
    if conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0] > 0:
        print(f"{DB_PATH} already has data; delete it to re-seed.")
        return

    for client_number, name in CLIENTS:
        services.create_client(conn, client_number, name)

    for client_number, principal, total_due, payments in LOANS:
        loan = services.create_loan(conn, client_number, principal, total_due)
        for amount, payment_reference, paid_on in payments:
            services.record_repayment(conn, loan["reference"], amount, payment_reference, paid_on)
        summary = services.get_loan_summary(conn, loan["reference"])
        print(f"{summary['reference']}  {summary['client_name']:<16} "
              f"due KES {summary['total_due']:>6,}  outstanding KES {summary['outstanding_balance']:>6,}")
    conn.close()


if __name__ == "__main__":
    main()
