"""Domain errors raised by the service layer.

Each class carries the HTTP status it should become; main.py reads it.
Subclasses inherit it, so e.g. `class OverpaymentError(BusinessRuleError)` is 400 for free.
"""


class LoanTrackerError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(LoanTrackerError):
    """A client or loan does not exist."""
    status_code = 404


class DuplicateError(LoanTrackerError):
    """A unique value (client number, payment reference) already exists."""
    status_code = 409


class BusinessRuleError(LoanTrackerError):
    """A request breaks a business rule, e.g. overpayment."""
    status_code = 400
