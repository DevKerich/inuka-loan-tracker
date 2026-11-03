"""Thin HTTP layer: validate input (schemas), call a service, return the result.
Errors raised by services are turned into HTTP responses in main.py."""
import sqlite3

from fastapi import APIRouter, Depends

from app import services
from app.db import get_db
from app.schemas import (
    ClientCreate, ClientOut, ErrorOut, LoanCreate, LoanOut,
    RepaymentCreate, RepaymentHistory, RepaymentRecorded,
)

router = APIRouter()

# Only used to document error responses on the /docs page.
NOT_FOUND = {404: {"model": ErrorOut, "description": "Client or loan not found"}}
DUPLICATE = {409: {"model": ErrorOut, "description": "Already recorded / registered"}}
RULE_BROKEN = {400: {"model": ErrorOut, "description": "Business rule broken, e.g. overpayment"}}


@router.post("/clients", response_model=ClientOut, status_code=201, tags=["Clients"], responses=DUPLICATE)
def register_client(body: ClientCreate, conn: sqlite3.Connection = Depends(get_db)):
    return services.create_client(conn, body.client_number, body.name)


@router.get("/clients/{client_number}", response_model=ClientOut, tags=["Clients"], responses=NOT_FOUND)
def get_client(client_number: str, conn: sqlite3.Connection = Depends(get_db)):
    return services.get_client(conn, client_number)


@router.post("/loans", response_model=LoanOut, status_code=201, tags=["Loans"], responses=NOT_FOUND)
def create_loan(body: LoanCreate, conn: sqlite3.Connection = Depends(get_db)):
    return services.create_loan(conn, body.client_number, body.principal, body.total_due)


@router.get("/loans", response_model=list[LoanOut], tags=["Loans"])
def list_loans(conn: sqlite3.Connection = Depends(get_db)):
    return services.list_loans(conn)


@router.get("/loans/{reference}", response_model=LoanOut, tags=["Loans"], responses=NOT_FOUND)
def get_loan(reference: str, conn: sqlite3.Connection = Depends(get_db)):
    return services.get_loan_summary(conn, reference)


@router.post(
    "/loans/{reference}/repayments",
    response_model=RepaymentRecorded,
    status_code=201,
    tags=["Repayments"],
    responses={**NOT_FOUND, **DUPLICATE, **RULE_BROKEN},
)
def record_repayment(reference: str, body: RepaymentCreate, conn: sqlite3.Connection = Depends(get_db)):
    return services.record_repayment(
        conn, reference, body.amount, body.payment_reference, body.payment_date
    )


@router.get(
    "/loans/{reference}/repayments", response_model=RepaymentHistory, tags=["Repayments"], responses=NOT_FOUND
)
def repayment_history(reference: str, conn: sqlite3.Connection = Depends(get_db)):
    return services.list_repayments(conn, reference)
