-- All money columns are INTEGER whole Kenyan shillings (KES). Never floats.
-- The outstanding balance is NOT stored: it is always total_due - SUM(repayments.amount).

CREATE TABLE IF NOT EXISTS clients (
    id             INTEGER PRIMARY KEY,
    client_number  TEXT    NOT NULL UNIQUE CHECK (client_number <> ''),
    name           TEXT    NOT NULL CHECK (name <> ''),
    created_at     TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS loans (
    id          INTEGER PRIMARY KEY,
    reference   TEXT    NOT NULL UNIQUE,
    client_id   INTEGER NOT NULL REFERENCES clients(id),
    principal   INTEGER NOT NULL CHECK (principal > 0),
    total_due   INTEGER NOT NULL CHECK (total_due >= principal),
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS repayments (
    id                 INTEGER PRIMARY KEY,
    loan_id            INTEGER NOT NULL REFERENCES loans(id),
    amount             INTEGER NOT NULL CHECK (amount > 0),
    payment_reference  TEXT    NOT NULL UNIQUE CHECK (payment_reference <> ''),  -- unique across ALL loans
    payment_date       TEXT    NOT NULL,         -- ISO date, e.g. 2026-11-02
    created_at         TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Speeds up SUM(amount) and history lookups for a loan.
CREATE INDEX IF NOT EXISTS idx_repayments_loan_id ON repayments(loan_id);
