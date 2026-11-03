from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.db import connect, init_db
from app.errors import LoanTrackerError
from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = connect()
    init_db(conn)  # creates tables if they don't exist yet
    conn.close()
    yield


app = FastAPI(
    title="Inuka Africa – Loan Repayment Tracker",
    description="Register loans, record repayments and see outstanding balances. "
    "All amounts are whole Kenyan shillings (KES). Fictional data only.",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(router)


# Every error response has the same shape: {"detail": "readable message"}.

@app.exception_handler(LoanTrackerError)
async def handle_domain_error(request: Request, exc: LoanTrackerError):
    # 404 / 409 / 400, taken from the error class itself (see errors.py).
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    # Pydantic reports a list of problems; join them into one readable sentence,
    # e.g. "amount: Input should be greater than 0".
    problems = [f"{err['loc'][-1]}: {err['msg']}" for err in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "; ".join(problems)})
