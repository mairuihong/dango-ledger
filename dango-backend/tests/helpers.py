"""测试辅助函数。"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.db import current_month, shift_month


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register(
    client: TestClient,
    username: str = "alice",
    password: str = "secret123",
) -> dict[str, Any]:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


def login(
    client: TestClient,
    username: str = "alice",
    password: str = "secret123",
) -> dict[str, Any]:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()


def create_account(
    client: TestClient,
    token: str,
    name: str = "现金",
    type_: str = "cash",
    initial_balance: int = 10000,
) -> dict[str, Any]:
    response = client.post(
        "/api/accounts",
        headers=auth_headers(token),
        json={
            "name": name,
            "type": type_,
            "initial_balance": initial_balance,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def list_accounts(client: TestClient, token: str) -> dict[str, Any]:
    response = client.get("/api/accounts", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    return response.json()


def get_account(client: TestClient, token: str, account_id: str) -> dict[str, Any]:
    data = list_accounts(client, token)
    for item in data["items"]:
        if item["id"] == account_id:
            return item
    raise AssertionError(f"账户不存在: {account_id}")


def list_categories(client: TestClient, token: str) -> list[dict[str, Any]]:
    response = client.get("/api/categories", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    return response.json()


def find_category(
    client: TestClient,
    token: str,
    name: str,
    kind: str | None = None,
) -> dict[str, Any]:
    for category in list_categories(client, token):
        if category["name"] == name and (kind is None or category["kind"] == kind):
            return category
    raise AssertionError(f"分类不存在: {name}")


def create_category(
    client: TestClient,
    token: str,
    name: str = "奶茶",
    kind: str = "expense",
    icon: str = "🧋",
    color: str = "#FF8A65",
) -> dict[str, Any]:
    response = client.post(
        "/api/categories",
        headers=auth_headers(token),
        json={"name": name, "kind": kind, "icon": icon, "color": color},
    )
    assert response.status_code == 200, response.text
    return response.json()


def create_transaction(
    client: TestClient,
    token: str,
    *,
    tx_type: str = "expense",
    amount: int = 3000,
    account_id: str,
    to_account_id: str | None = None,
    category_id: str | None = None,
    occurred_at: str | None = None,
    note: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": tx_type,
        "amount": amount,
        "account_id": account_id,
        "to_account_id": to_account_id,
        "category_id": category_id,
        "note": note,
    }
    if occurred_at is not None:
        payload["occurred_at"] = occurred_at
    response = client.post(
        "/api/transactions",
        headers=auth_headers(token),
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()


def list_transactions(
    client: TestClient,
    token: str,
    **params: Any,
) -> dict[str, Any]:
    response = client.get(
        "/api/transactions",
        headers=auth_headers(token),
        params=params,
    )
    assert response.status_code == 200, response.text
    return response.json()


def month_key(offset: int = 0) -> str:
    """相对当前月份偏移的 YYYY-MM。"""

    return shift_month(current_month(), offset)
