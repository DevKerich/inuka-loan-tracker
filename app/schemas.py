"""Request/response shapes. Pydantic rejects bad input with a 422 before
any service code runs (e.g. amount <= 0, decimals, blank text, missing fields)."""
from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.services import MAX_AMOUNT_KES

# Whitespace is stripped *before* the length check, so "   " counts as empty.
ClientNumber = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
PaymentReference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]

# Whole KES. strict=True rejects true/false and "3000" strings;
# le= keeps values well inside SQLite's 64-bit INTEGER range.
Kes = Annotated[int, Field(strict=True, gt=0, le=MAX_AMOUNT_KES)]


class ClientCreate(BaseModel):
    client_number: ClientNumber = Field(examples=["CL-1005"])
    name: Name = Field(examples=["Akinyi Atieno"])


class ClientOut(BaseModel):
    client_number: str
    name: str
    created_at: str


class LoanCreate(BaseModel):
    client_number: ClientNumber = Field(examples=["CL-1005"])
    principal: Kes = Field(description="Amount lent, whole KES", examples=[10000])
    total_due: Kes = Field(description="Principal plus interest/fees, whole KES", examples=[11500])

    @model_validator(mode="after")
    def total_due_covers_principal(self):
        if self.total_due < self.principal:
            raise ValueError("total_due cannot be less than principal")
        return self


class LoanOut(BaseModel):
    reference: str
    client_number: str
    client_name: str
    principal: int
    total_due: int
    total_repaid: int
    outstanding_balance: int
    created_at: str


class RepaymentCreate(BaseModel):
    amount: Kes = Field(description="Whole KES, must be > 0", examples=[3000])
    payment_reference: PaymentReference = Field(examples=["TKB7X2M9QP"])
    payment_date: date = Field(examples=["2026-11-02"])


class RepaymentOut(BaseModel):
    payment_reference: str
    amount: int
    payment_date: date
    recorded_at: str


class RepaymentRecorded(BaseModel):
    repayment: RepaymentOut
    loan: LoanOut


class RepaymentHistory(BaseModel):
    loan: LoanOut
    repayments: list[RepaymentOut]


class ErrorOut(BaseModel):
    detail: str
