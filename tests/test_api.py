"""End-to-end checks through HTTP: status codes and error messages."""


def create_loan(api, client_number="CL-2001", total_due=10_000):
    api.post("/clients", json={"client_number": client_number, "name": "Njeri Wambui"})
    response = api.post(
        "/loans", json={"client_number": client_number, "principal": total_due, "total_due": total_due}
    )
    assert response.status_code == 201
    return response.json()["reference"]


def pay(api, ref, amount, payment_reference="PAY-001"):
    return api.post(
        f"/loans/{ref}/repayments",
        json={"amount": amount, "payment_reference": payment_reference, "payment_date": "2026-11-02"},
    )


def test_api_scenario_1_repayment_returns_new_balance(api):
    ref = create_loan(api, total_due=10_000)

    response = pay(api, ref, 3_000)

    assert response.status_code == 201
    assert response.json()["loan"]["outstanding_balance"] == 7_000


def test_api_scenario_2_duplicate_reference_returns_409(api):
    ref = create_loan(api)
    pay(api, ref, 3_000, "PAY-DUP")

    response = pay(api, ref, 3_000, "PAY-DUP")

    assert response.status_code == 409
    assert "already been recorded" in response.json()["detail"]
    history = api.get(f"/loans/{ref}/repayments").json()
    assert len(history["repayments"]) == 1
    assert history["loan"]["outstanding_balance"] == 7_000


def test_api_scenario_3_overpayment_returns_400_and_balance_unchanged(api):
    ref = create_loan(api, total_due=1_000)

    response = pay(api, ref, 1_500)

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Repayment of KES 1,500 exceeds the outstanding balance of KES 1,000."
    )
    assert api.get(f"/loans/{ref}").json()["outstanding_balance"] == 1_000


def test_api_zero_amount_returns_422(api):
    ref = create_loan(api)
    assert pay(api, ref, 0).status_code == 422
    assert pay(api, ref, -100).status_code == 422


def test_api_decimal_amount_returns_422(api):
    ref = create_loan(api)
    assert pay(api, ref, 100.5).status_code == 422


def test_api_unknown_loan_returns_404(api):
    response = pay(api, "LN-NOPE", 1_000)
    assert response.status_code == 404
    assert response.json()["detail"] == "Loan 'LN-NOPE' does not exist."


def test_api_loan_for_unknown_client_returns_404(api):
    response = api.post("/loans", json={"client_number": "CL-0000", "principal": 1_000, "total_due": 1_000})
    assert response.status_code == 404


def test_api_total_due_below_principal_returns_422(api):
    api.post("/clients", json={"client_number": "CL-3001", "name": "Kibet Rotich"})
    response = api.post("/loans", json={"client_number": "CL-3001", "principal": 5_000, "total_due": 4_000})
    assert response.status_code == 422


def test_api_duplicate_client_returns_409(api):
    body = {"client_number": "CL-4001", "name": "Achieng Odhiambo"}
    assert api.post("/clients", json=body).status_code == 201
    assert api.post("/clients", json=body).status_code == 409


def test_api_repayment_history_lists_payments_in_date_order(api):
    ref = create_loan(api)
    api.post(f"/loans/{ref}/repayments",
             json={"amount": 2_000, "payment_reference": "PAY-B", "payment_date": "2026-10-15"})
    api.post(f"/loans/{ref}/repayments",
             json={"amount": 1_000, "payment_reference": "PAY-A", "payment_date": "2026-09-15"})

    history = api.get(f"/loans/{ref}/repayments").json()

    assert [r["payment_reference"] for r in history["repayments"]] == ["PAY-A", "PAY-B"]
    assert history["loan"]["total_repaid"] == 3_000
    assert history["loan"]["outstanding_balance"] == 7_000


# ---------- Regression tests from code review ----------

def test_api_blank_payment_reference_returns_422_and_stores_nothing(api):
    ref = create_loan(api)

    response = pay(api, ref, 1_000, payment_reference="   ")

    assert response.status_code == 422
    assert api.get(f"/loans/{ref}/repayments").json()["repayments"] == []


def test_api_blank_client_number_or_name_returns_422(api):
    assert api.post("/clients", json={"client_number": "   ", "name": "Wafula"}).status_code == 422
    assert api.post("/clients", json={"client_number": "CL-7001", "name": "  "}).status_code == 422


def test_api_huge_amount_returns_422_not_500(api):
    api.post("/clients", json={"client_number": "CL-8001", "name": "Nyambura Mwangi"})
    response = api.post("/loans", json={"client_number": "CL-8001", "principal": 1, "total_due": 10**20})
    assert response.status_code == 422


def test_api_boolean_or_string_amount_returns_422(api):
    ref = create_loan(api)
    assert pay(api, ref, True, "PAY-BOOL").status_code == 422
    assert pay(api, ref, "3000", "PAY-STR").status_code == 422


def test_api_validation_errors_use_same_detail_shape(api):
    ref = create_loan(api)

    response = pay(api, ref, 0)

    assert response.status_code == 422
    assert response.json() == {"detail": "amount: Input should be greater than 0"}


def test_new_error_subclass_inherits_its_parents_status_code():
    """Adding e.g. OverpaymentError(BusinessRuleError) must give 400, not crash with a 500."""
    import asyncio

    from app.errors import BusinessRuleError
    from app.main import handle_domain_error

    class OverpaymentError(BusinessRuleError):
        pass

    response = asyncio.run(handle_domain_error(None, OverpaymentError("too much")))

    assert response.status_code == 400
    assert response.body == b'{"detail":"too much"}'
