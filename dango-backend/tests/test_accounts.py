"""账户接口测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.helpers import (
    auth_headers,
    create_account,
    create_transaction,
    find_category,
    get_account,
    list_accounts,
    register,
)


def _create_expense(client, token, account_id, amount=3000):
    category = find_category(client, token, "餐饮", "expense")
    return create_transaction(
        client,
        token,
        tx_type="expense",
        amount=amount,
        account_id=account_id,
        category_id=category["id"],
    )


def test_empty_account_list(client: TestClient) -> None:
    token = register(client)["token"]
    payload = list_accounts(client, token)
    assert payload == {"items": [], "total_balance": 0}


def test_create_account_balance_equals_initial(client: TestClient) -> None:
    token = register(client)["token"]
    account = create_account(client, token, "现金", "cash", 12345)
    assert account["name"] == "现金"
    assert account["type"] == "cash"
    assert account["initial_balance"] == 12345
    assert account["balance"] == 12345
    assert account["sort"] == 0
    assert account["id"]


def test_account_list_total_balance(client: TestClient) -> None:
    token = register(client)["token"]
    create_account(client, token, "现金", "cash", 10000)
    create_account(client, token, "银行卡", "bank", 5000)
    payload = list_accounts(client, token)
    assert len(payload["items"]) == 2
    assert payload["total_balance"] == 15000


def test_patch_account_name(client: TestClient) -> None:
    token = register(client)["token"]
    account = create_account(client, token)
    response = client.put(
        f"/api/accounts/{account['id']}",
        headers=auth_headers(token),
        json={"name": "零钱包"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "零钱包"
    assert get_account(client, token, account["id"])["name"] == "零钱包"


def test_patch_initial_balance_adjusts_current_balance(client: TestClient) -> None:
    token = register(client)["token"]
    account = create_account(client, token, initial_balance=10000)
    _create_expense(client, token, account["id"], 3000)
    assert get_account(client, token, account["id"])["balance"] == 7000

    response = client.put(
        f"/api/accounts/{account['id']}",
        headers=auth_headers(token),
        json={"initial_balance": 15000},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["initial_balance"] == 15000
    # 初始余额增加 5000，当前余额也应增加 5000
    assert payload["balance"] == 12000


def test_patch_account_sort_changes_order(client: TestClient) -> None:
    token = register(client)["token"]
    first = create_account(client, token, "A", initial_balance=0)
    second = create_account(client, token, "B", initial_balance=0)
    third = create_account(client, token, "C", initial_balance=0)
    assert [item["id"] for item in list_accounts(client, token)["items"]] == [
        first["id"],
        second["id"],
        third["id"],
    ]

    response = client.put(
        f"/api/accounts/{third['id']}",
        headers=auth_headers(token),
        json={"sort": -1},
    )
    assert response.status_code == 200
    assert response.json()["sort"] == -1
    assert list_accounts(client, token)["items"][0]["id"] == third["id"]


def test_delete_empty_account_writes_tombstone(client: TestClient, db) -> None:
    token = register(client)["token"]
    account = create_account(client, token)
    response = client.delete(f"/api/accounts/{account['id']}", headers=auth_headers(token))
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert list_accounts(client, token)["items"] == []

    row = db.fetchone("SELECT deleted_at FROM accounts WHERE id = ?", (account["id"],))
    assert row is not None and row["deleted_at"]


def test_delete_account_with_transaction_conflict(client: TestClient) -> None:
    token = register(client)["token"]
    account = create_account(client, token)
    _create_expense(client, token, account["id"])
    response = client.delete(f"/api/accounts/{account['id']}", headers=auth_headers(token))
    assert response.status_code == 409
    assert "流水" in response.json()["detail"]


def test_delete_account_after_transactions_removed(client: TestClient) -> None:
    token = register(client)["token"]
    account = create_account(client, token)
    transaction = _create_expense(client, token, account["id"])
    assert (
        client.delete(f"/api/accounts/{account['id']}", headers=auth_headers(token)).status_code
        == 409
    )
    assert (
        client.delete(
            f"/api/transactions/{transaction['id']}", headers=auth_headers(token)
        ).status_code
        == 200
    )
    response = client.delete(f"/api/accounts/{account['id']}", headers=auth_headers(token))
    assert response.status_code == 200
    assert list_accounts(client, token)["items"] == []


def test_delete_destination_account_with_transfer_conflict(
    client: TestClient,
) -> None:
    token = register(client)["token"]
    source = create_account(client, token, "转出", initial_balance=10000)
    target = create_account(client, token, "转入", initial_balance=0)
    create_transaction(
        client,
        token,
        tx_type="transfer",
        amount=4000,
        account_id=source["id"],
        to_account_id=target["id"],
    )
    response = client.delete(f"/api/accounts/{target['id']}", headers=auth_headers(token))
    assert response.status_code == 409


def test_recalc_repairs_balances(client: TestClient, db) -> None:
    token = register(client)["token"]
    source = create_account(client, token, "现金", initial_balance=10000)
    target = create_account(client, token, "银行卡", initial_balance=5000)
    _create_expense(client, token, source["id"], 3000)
    create_transaction(
        client,
        token,
        tx_type="transfer",
        amount=2000,
        account_id=source["id"],
        to_account_id=target["id"],
    )

    # 人为破坏缓存余额，重算应按流水恢复
    with db.transaction() as conn:
        conn.execute("UPDATE accounts SET balance = 999999")

    response = client.post("/api/accounts/recalc", headers=auth_headers(token))
    assert response.status_code == 200
    payload = response.json()
    balances = {item["id"]: item["balance"] for item in payload["items"]}
    assert balances[source["id"]] == 10000 - 3000 - 2000
    assert balances[target["id"]] == 5000 + 2000
    assert payload["total_balance"] == 12000


def test_recalc_without_transactions_keeps_initial(client: TestClient) -> None:
    token = register(client)["token"]
    account = create_account(client, token, initial_balance=8888)
    response = client.post("/api/accounts/recalc", headers=auth_headers(token))
    assert response.status_code == 200
    assert response.json()["items"][0]["balance"] == 8888
    assert response.json()["items"][0]["id"] == account["id"]


def test_accounts_are_isolated_between_users(client: TestClient) -> None:
    alice = register(client, "alice")["token"]
    bob = register(client, "bob")["token"]
    alice_account = create_account(client, alice, "Alice 现金", initial_balance=20000)

    assert list_accounts(client, bob) == {"items": [], "total_balance": 0}

    patch = client.put(
        f"/api/accounts/{alice_account['id']}",
        headers=auth_headers(bob),
        json={"name": "篡改"},
    )
    assert patch.status_code == 404

    delete = client.delete(f"/api/accounts/{alice_account['id']}", headers=auth_headers(bob))
    assert delete.status_code == 404

    assert list_accounts(client, alice)["items"][0]["name"] == "Alice 现金"


def test_create_account_validation(client: TestClient) -> None:
    token = register(client)["token"]
    response = client.post(
        "/api/accounts",
        headers=auth_headers(token),
        json={"name": "   ", "type": "cash", "initial_balance": 0},
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
