"""预算与统计接口测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.helpers import (
    auth_headers,
    create_account,
    create_category,
    create_transaction,
    find_category,
    month_key,
    register,
)


def _overview(client: TestClient, token: str, month: str | None = None) -> dict:
    params = {"month": month} if month else {}
    response = client.get("/api/stats/overview", headers=auth_headers(token), params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _trend(client: TestClient, token: str, months: int = 3) -> dict:
    response = client.get(
        "/api/stats/monthly-trend",
        headers=auth_headers(token),
        params={"months": months},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_budget_default_is_zero(client: TestClient) -> None:
    token = register(client)["token"]
    response = client.get("/api/budgets", headers=auth_headers(token))
    assert response.status_code == 200
    assert response.json() == {"month": month_key(0), "amount": 0}


def test_budget_put_and_get(client: TestClient) -> None:
    token = register(client)["token"]
    response = client.put(
        "/api/budgets",
        headers=auth_headers(token),
        json={"month": "2024-04", "amount": 200000},
    )
    assert response.status_code == 200
    assert response.json() == {"month": "2024-04", "amount": 200000}

    fetched = client.get(
        "/api/budgets",
        headers=auth_headers(token),
        params={"month": "2024-04"},
    )
    assert fetched.status_code == 200
    assert fetched.json() == {"month": "2024-04", "amount": 200000}


def test_budget_upsert(client: TestClient) -> None:
    token = register(client)["token"]
    for amount in (100000, 150000):
        response = client.put(
            "/api/budgets",
            headers=auth_headers(token),
            json={"month": "2024-04", "amount": amount},
        )
        assert response.status_code == 200
    fetched = client.get(
        "/api/budgets",
        headers=auth_headers(token),
        params={"month": "2024-04"},
    )
    assert fetched.json()["amount"] == 150000


def test_budget_validation(client: TestClient) -> None:
    token = register(client)["token"]
    negative = client.put(
        "/api/budgets",
        headers=auth_headers(token),
        json={"month": "2024-04", "amount": -1},
    )
    assert negative.status_code == 422

    invalid_month = client.get(
        "/api/budgets",
        headers=auth_headers(token),
        params={"month": "2024-13"},
    )
    assert invalid_month.status_code == 422


def test_budget_is_isolated(client: TestClient) -> None:
    alice = register(client, "alice")["token"]
    bob = register(client, "bob")["token"]
    client.put(
        "/api/budgets",
        headers=auth_headers(alice),
        json={"month": "2024-04", "amount": 500000},
    )
    bob_budget = client.get(
        "/api/budgets",
        headers=auth_headers(bob),
        params={"month": "2024-04"},
    )
    assert bob_budget.json() == {"month": "2024-04", "amount": 0}
    # 互不覆盖
    client.put(
        "/api/budgets",
        headers=auth_headers(bob),
        json={"month": "2024-04", "amount": 100},
    )
    alice_budget = client.get(
        "/api/budgets",
        headers=auth_headers(alice),
        params={"month": "2024-04"},
    )
    assert alice_budget.json()["amount"] == 500000


def test_overview_empty_month(client: TestClient) -> None:
    token = register(client)["token"]
    payload = _overview(client, token, "2024-04")
    assert payload == {
        "month": "2024-04",
        "income": 0,
        "expense": 0,
        "balance": 0,
        "transaction_count": 0,
        "categories": [],
        "daily": [],
    }


def test_overview_income_expense_balance_and_count(client: TestClient) -> None:
    token = register(client)["token"]
    account = create_account(client, token, initial_balance=100000)
    food = create_category(client, token, "大餐", "expense")
    shopping = create_category(client, token, "购物", "expense")
    salary = find_category(client, token, "工资", "income")

    create_transaction(
        client,
        token,
        tx_type="expense",
        amount=20000,
        account_id=account["id"],
        category_id=food["id"],
        occurred_at="2024-04-05",
    )
    create_transaction(
        client,
        token,
        tx_type="expense",
        amount=30000,
        account_id=account["id"],
        category_id=shopping["id"],
        occurred_at="2024-04-06",
    )
    create_transaction(
        client,
        token,
        tx_type="income",
        amount=50000,
        account_id=account["id"],
        category_id=salary["id"],
        occurred_at="2024-04-05",
    )

    payload = _overview(client, token, "2024-04")
    assert set(payload) == {
        "month",
        "income",
        "expense",
        "balance",
        "transaction_count",
        "categories",
        "daily",
    }
    assert payload["income"] == 50000
    assert payload["expense"] == 50000
    assert payload["balance"] == 0
    assert payload["transaction_count"] == 3

    categories = payload["categories"]
    assert [item["name"] for item in categories] == ["购物", "大餐"]
    assert [item["amount"] for item in categories] == [30000, 20000]
    assert [item["percent"] for item in categories] == [60.0, 40.0]
    assert [item["count"] for item in categories] == [1, 1]
    assert sum(item["percent"] for item in categories) == 100.0
    assert set(categories[0]) == {
        "category_id",
        "name",
        "icon",
        "color",
        "amount",
        "percent",
        "count",
    }

    daily = payload["daily"]
    assert [item["date"] for item in daily] == ["2024-04-05", "2024-04-06"]
    assert daily[0] == {
        "date": "2024-04-05",
        "income": 50000,
        "expense": 20000,
        "balance": 30000,
    }
    assert daily[1] == {
        "date": "2024-04-06",
        "income": 0,
        "expense": 30000,
        "balance": -30000,
    }


def test_overview_excludes_transfers(client: TestClient) -> None:
    token = register(client)["token"]
    source = create_account(client, token, "现金", initial_balance=10000)
    target = create_account(client, token, "银行卡", initial_balance=0)
    create_transaction(
        client,
        token,
        tx_type="transfer",
        amount=5000,
        account_id=source["id"],
        to_account_id=target["id"],
        occurred_at="2024-04-10",
    )
    payload = _overview(client, token, "2024-04")
    assert payload["income"] == 0
    assert payload["expense"] == 0
    assert payload["balance"] == 0
    assert payload["transaction_count"] == 0
    assert payload["categories"] == []
    assert payload["daily"] == []


def test_overview_only_uses_requested_month(client: TestClient) -> None:
    token = register(client)["token"]
    account = create_account(client, token, initial_balance=100000)
    category = find_category(client, token, "餐饮", "expense")
    create_transaction(
        client,
        token,
        amount=1000,
        account_id=account["id"],
        category_id=category["id"],
        occurred_at="2024-04-01",
    )
    create_transaction(
        client,
        token,
        amount=2000,
        account_id=account["id"],
        category_id=category["id"],
        occurred_at="2024-05-01",
    )
    april = _overview(client, token, "2024-04")
    may = _overview(client, token, "2024-05")
    assert april["expense"] == 1000
    assert may["expense"] == 2000


def test_overview_excludes_deleted_transactions(client: TestClient) -> None:
    token = register(client)["token"]
    account = create_account(client, token, initial_balance=100000)
    category = find_category(client, token, "餐饮", "expense")
    created = create_transaction(
        client,
        token,
        amount=1234,
        account_id=account["id"],
        category_id=category["id"],
        occurred_at="2024-04-09",
    )
    client.delete(f"/api/transactions/{created['id']}", headers=auth_headers(token))
    payload = _overview(client, token, "2024-04")
    assert payload["expense"] == 0
    assert payload["transaction_count"] == 0


def test_overview_default_month_is_current(client: TestClient) -> None:
    token = register(client)["token"]
    account = create_account(client, token, initial_balance=100000)
    category = find_category(client, token, "餐饮", "expense")
    create_transaction(
        client,
        token,
        amount=4321,
        account_id=account["id"],
        category_id=category["id"],
        occurred_at=f"{month_key(0)}-03",
    )
    payload = _overview(client, token)
    assert payload["month"] == month_key(0)
    assert payload["expense"] == 4321


def test_overview_is_isolated(client: TestClient) -> None:
    alice = register(client, "alice")["token"]
    bob = register(client, "bob")["token"]
    account = create_account(client, alice, initial_balance=10000)
    category = find_category(client, alice, "餐饮", "expense")
    create_transaction(
        client,
        alice,
        amount=1000,
        account_id=account["id"],
        category_id=category["id"],
        occurred_at="2024-04-01",
    )
    assert _overview(client, alice, "2024-04")["expense"] == 1000
    assert _overview(client, bob, "2024-04")["expense"] == 0


def test_monthly_trend_shape_and_values(client: TestClient) -> None:
    token = register(client)["token"]
    account = create_account(client, token, initial_balance=100000)
    expense_category = find_category(client, token, "餐饮", "expense")
    income_category = find_category(client, token, "工资", "income")

    previous = month_key(-1)
    current = month_key(0)
    create_transaction(
        client,
        token,
        tx_type="expense",
        amount=2000,
        account_id=account["id"],
        category_id=expense_category["id"],
        occurred_at=f"{previous}-05",
    )
    create_transaction(
        client,
        token,
        tx_type="income",
        amount=8000,
        account_id=account["id"],
        category_id=income_category["id"],
        occurred_at=f"{current}-05",
    )
    create_transaction(
        client,
        token,
        tx_type="expense",
        amount=3000,
        account_id=account["id"],
        category_id=expense_category["id"],
        occurred_at=f"{current}-06",
    )

    payload = _trend(client, token, months=3)
    assert payload["months"] == 3
    assert payload["start_month"] == month_key(-2)
    assert payload["end_month"] == month_key(0)
    assert len(payload["items"]) == 3
    assert set(payload["items"][0]) == {"month", "income", "expense", "balance"}

    first, second, third = payload["items"]
    assert first == {
        "month": month_key(-2),
        "income": 0,
        "expense": 0,
        "balance": 0,
    }
    assert second == {
        "month": previous,
        "income": 0,
        "expense": 2000,
        "balance": -2000,
    }
    assert third == {
        "month": current,
        "income": 8000,
        "expense": 3000,
        "balance": 5000,
    }


def test_monthly_trend_excludes_transfers(client: TestClient) -> None:
    token = register(client)["token"]
    source = create_account(client, token, "现金", initial_balance=10000)
    target = create_account(client, token, "银行卡", initial_balance=0)
    create_transaction(
        client,
        token,
        tx_type="transfer",
        amount=5000,
        account_id=source["id"],
        to_account_id=target["id"],
        occurred_at=f"{month_key(0)}-10",
    )
    payload = _trend(client, token, months=1)
    assert payload["items"][0]["income"] == 0
    assert payload["items"][0]["expense"] == 0


def test_monthly_trend_is_isolated(client: TestClient) -> None:
    alice = register(client, "alice")["token"]
    bob = register(client, "bob")["token"]
    account = create_account(client, alice, initial_balance=10000)
    category = find_category(client, alice, "餐饮", "expense")
    create_transaction(
        client,
        alice,
        amount=1000,
        account_id=account["id"],
        category_id=category["id"],
        occurred_at=f"{month_key(0)}-01",
    )
    alice_trend = _trend(client, alice, months=1)
    bob_trend = _trend(client, bob, months=1)
    assert alice_trend["items"][0]["expense"] == 1000
    assert bob_trend["items"][0]["expense"] == 0


def test_monthly_trend_validation(client: TestClient) -> None:
    token = register(client)["token"]
    response = client.get(
        "/api/stats/monthly-trend",
        headers=auth_headers(token),
        params={"months": 0},
    )
    assert response.status_code == 422
