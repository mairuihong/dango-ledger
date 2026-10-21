"""流水接口测试：CRUD、分页搜索、转账配对、余额联动。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.helpers import (
    auth_headers,
    create_account,
    create_category,
    create_transaction,
    find_category,
    get_account,
    list_transactions,
    register,
)


def _setup(client: TestClient, source_initial: int = 10000, target_initial: int = 0):
    token = register(client)["token"]
    source = create_account(client, token, "现金", "cash", source_initial)
    target = create_account(client, token, "银行卡", "bank", target_initial)
    expense_category = find_category(client, token, "餐饮", "expense")
    income_category = find_category(client, token, "工资", "income")
    return token, source, target, expense_category, income_category


def test_create_expense_updates_balance_and_list(client: TestClient) -> None:
    token, source, _, expense_category, _ = _setup(client)
    created = create_transaction(
        client,
        token,
        tx_type="expense",
        amount=3000,
        account_id=source["id"],
        category_id=expense_category["id"],
        note="午饭",
    )
    assert created["type"] == "expense"
    assert created["amount"] == 3000
    assert created["account_id"] == source["id"]
    assert created["category_name"] == "餐饮"
    assert get_account(client, token, source["id"])["balance"] == 7000

    listing = list_transactions(client, token)
    assert listing["total"] == 1
    assert listing["page"] == 1
    assert listing["page_size"] == 20
    assert listing["items"][0]["id"] == created["id"]


def test_create_income_updates_balance(client: TestClient) -> None:
    token, source, _, _, income_category = _setup(client)
    create_transaction(
        client,
        token,
        tx_type="income",
        amount=5000,
        account_id=source["id"],
        category_id=income_category["id"],
    )
    assert get_account(client, token, source["id"])["balance"] == 15000


def test_create_transfer_creates_pair_and_moves_balances(
    client: TestClient, db
) -> None:
    token, source, target, _, _ = _setup(client)
    created = create_transaction(
        client,
        token,
        tx_type="transfer",
        amount=4000,
        account_id=source["id"],
        to_account_id=target["id"],
        note="转到银行卡",
    )
    assert created["type"] == "transfer"
    assert created["category_id"] is None
    assert created["to_account_id"] == target["id"]

    assert get_account(client, token, source["id"])["balance"] == 6000
    assert get_account(client, token, target["id"])["balance"] == 4000
    assert list_accounts_total(client, token) == 10000

    rows = db.fetchall("SELECT * FROM transactions WHERE deleted_at IS NULL")
    assert len(rows) == 2
    assert {row["type"] for row in rows} == {"transfer", "transfer_in"}
    pair = next(row for row in rows if row["type"] == "transfer_in")
    assert pair["account_id"] == target["id"]
    assert pair["to_account_id"] == source["id"]
    assert pair["amount"] == 4000


def list_accounts_total(client: TestClient, token: str) -> int:
    from tests.helpers import list_accounts

    return list_accounts(client, token)["total_balance"]


def test_transfer_requires_destination(client: TestClient) -> None:
    token, source, _, _, _ = _setup(client)
    response = client.post(
        "/api/transactions",
        headers=auth_headers(token),
        json={"type": "transfer", "amount": 1000, "account_id": source["id"]},
    )
    assert response.status_code == 400


def test_transfer_rejects_same_account(client: TestClient) -> None:
    token, source, _, _, _ = _setup(client)
    response = client.post(
        "/api/transactions",
        headers=auth_headers(token),
        json={
            "type": "transfer",
            "amount": 1000,
            "account_id": source["id"],
            "to_account_id": source["id"],
        },
    )
    assert response.status_code == 400


def test_non_transfer_rejects_destination(client: TestClient) -> None:
    token, source, target, _, _ = _setup(client)
    response = client.post(
        "/api/transactions",
        headers=auth_headers(token),
        json={
            "type": "expense",
            "amount": 1000,
            "account_id": source["id"],
            "to_account_id": target["id"],
        },
    )
    assert response.status_code == 400


def test_transfer_to_foreign_account_rejected(client: TestClient) -> None:
    alice = register(client, "alice")["token"]
    bob = register(client, "bob")["token"]
    alice_account = create_account(client, alice, "Alice", initial_balance=10000)
    bob_account = create_account(client, bob, "Bob", initial_balance=10000)
    response = client.post(
        "/api/transactions",
        headers=auth_headers(alice),
        json={
            "type": "transfer",
            "amount": 1000,
            "account_id": alice_account["id"],
            "to_account_id": bob_account["id"],
        },
    )
    assert response.status_code == 404


def test_transaction_month_filter(client: TestClient) -> None:
    token = register(client)["token"]
    account = create_account(client, token, initial_balance=100000)
    category = find_category(client, token, "餐饮", "expense")
    for occurred_at, amount in (
        ("2024-01-10", 1000),
        ("2024-02-10", 2000),
    ):
        create_transaction(
            client,
            token,
            amount=amount,
            account_id=account["id"],
            category_id=category["id"],
            occurred_at=occurred_at,
        )

    january = list_transactions(client, token, month="2024-01")
    february = list_transactions(client, token, month="2024-02")
    everything = list_transactions(client, token)
    assert january["total"] == 1
    assert january["items"][0]["amount"] == 1000
    assert february["total"] == 1
    assert everything["total"] == 2


def test_keyword_matches_note(client: TestClient) -> None:
    token, source, _, expense_category, _ = _setup(client)
    create_transaction(
        client,
        token,
        amount=1500,
        account_id=source["id"],
        category_id=expense_category["id"],
        note="珍珠奶茶",
    )
    create_transaction(
        client,
        token,
        amount=800,
        account_id=source["id"],
        category_id=expense_category["id"],
        note="公交",
    )
    matched = list_transactions(client, token, keyword="奶茶")
    assert matched["total"] == 1
    assert matched["items"][0]["note"] == "珍珠奶茶"
    assert list_transactions(client, token, keyword="不存在")["total"] == 0


def test_keyword_matches_category_name(client: TestClient) -> None:
    token, source, _, expense_category, _ = _setup(client)
    coffee = create_category(client, token, "咖啡", "expense", "☕", "#795548")
    create_transaction(
        client,
        token,
        amount=2500,
        account_id=source["id"],
        category_id=coffee["id"],
        note="上午",
    )
    create_transaction(
        client,
        token,
        amount=900,
        account_id=source["id"],
        category_id=expense_category["id"],
        note="下午",
    )
    matched = list_transactions(client, token, keyword="咖啡")
    assert matched["total"] == 1
    assert matched["items"][0]["category_name"] == "咖啡"


def test_keyword_escapes_like_wildcards(client: TestClient) -> None:
    token, source, _, expense_category, _ = _setup(client)
    create_transaction(
        client,
        token,
        amount=1000,
        account_id=source["id"],
        category_id=expense_category["id"],
        note="折扣100%",
    )
    assert list_transactions(client, token, keyword="%")["total"] == 1
    assert list_transactions(client, token, keyword="_")["total"] == 0


def test_transaction_pagination(client: TestClient) -> None:
    token = register(client)["token"]
    account = create_account(client, token, initial_balance=100000)
    category = find_category(client, token, "餐饮", "expense")
    for day in range(1, 6):
        create_transaction(
            client,
            token,
            amount=day * 100,
            account_id=account["id"],
            category_id=category["id"],
            occurred_at=f"2024-03-0{day}",
            note=f"第{day}笔",
        )

    page = list_transactions(client, token, page=2, page_size=2)
    assert page["total"] == 5
    assert page["page"] == 2
    assert page["page_size"] == 2
    assert [item["occurred_at"] for item in page["items"]] == [
        "2024-03-03",
        "2024-03-02",
    ]


def test_transfer_pair_hidden_from_list(client: TestClient) -> None:
    token, source, target, _, _ = _setup(client)
    create_transaction(
        client,
        token,
        tx_type="transfer",
        amount=3000,
        account_id=source["id"],
        to_account_id=target["id"],
    )
    listing = list_transactions(client, token)
    assert listing["total"] == 1
    assert len(listing["items"]) == 1
    assert listing["items"][0]["type"] == "transfer"
    assert listing["items"][0]["to_account_name"] == "银行卡"


def test_patch_expense_amount_rolls_back_old_delta(client: TestClient) -> None:
    token, source, _, expense_category, _ = _setup(client)
    created = create_transaction(
        client,
        token,
        amount=3000,
        account_id=source["id"],
        category_id=expense_category["id"],
    )
    assert get_account(client, token, source["id"])["balance"] == 7000

    response = client.put(
        f"/api/transactions/{created['id']}",
        headers=auth_headers(token),
        json={"amount": 5000},
    )
    assert response.status_code == 200
    assert response.json()["amount"] == 5000
    assert get_account(client, token, source["id"])["balance"] == 5000


def test_patch_expense_category_date_note(client: TestClient) -> None:
    token, source, _, expense_category, _ = _setup(client)
    created = create_transaction(
        client,
        token,
        amount=3000,
        account_id=source["id"],
        category_id=expense_category["id"],
        occurred_at="2024-01-10",
        note="旧备注",
    )
    coffee = create_category(client, token, "咖啡", "expense", "☕", "#795548")
    response = client.put(
        f"/api/transactions/{created['id']}",
        headers=auth_headers(token),
        json={
            "category_id": coffee["id"],
            "occurred_at": "2024-02-15T12:30:00",
            "note": "新备注",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["category_id"] == coffee["id"]
    assert payload["category_name"] == "咖啡"
    assert payload["occurred_at"] == "2024-02-15T12:30:00"
    assert payload["note"] == "新备注"
    assert get_account(client, token, source["id"])["balance"] == 7000


def test_patch_income_amount(client: TestClient) -> None:
    token, source, _, _, income_category = _setup(client)
    created = create_transaction(
        client,
        token,
        tx_type="income",
        amount=3000,
        account_id=source["id"],
        category_id=income_category["id"],
    )
    assert get_account(client, token, source["id"])["balance"] == 13000
    response = client.put(
        f"/api/transactions/{created['id']}",
        headers=auth_headers(token),
        json={"amount": 2000},
    )
    assert response.status_code == 200
    assert get_account(client, token, source["id"])["balance"] == 12000


def test_patch_transfer_syncs_pair_and_balances(client: TestClient, db) -> None:
    token, source, target, _, _ = _setup(client)
    created = create_transaction(
        client,
        token,
        tx_type="transfer",
        amount=3000,
        account_id=source["id"],
        to_account_id=target["id"],
    )
    response = client.put(
        f"/api/transactions/{created['id']}",
        headers=auth_headers(token),
        json={"amount": 5000, "note": "改金额"},
    )
    assert response.status_code == 200
    assert response.json()["amount"] == 5000
    assert response.json()["type"] == "transfer"

    assert get_account(client, token, source["id"])["balance"] == 5000
    assert get_account(client, token, target["id"])["balance"] == 5000
    assert list_accounts_total(client, token) == 10000

    rows = db.fetchall("SELECT * FROM transactions WHERE deleted_at IS NULL")
    assert len(rows) == 2
    assert {row["amount"] for row in rows} == {5000}
    assert {row["note"] for row in rows} == {"改金额"}


def test_patch_transfer_by_pair_id(client: TestClient, db) -> None:
    token, source, target, _, _ = _setup(client)
    create_transaction(
        client,
        token,
        tx_type="transfer",
        amount=3000,
        account_id=source["id"],
        to_account_id=target["id"],
    )
    pair = db.fetchone(
        "SELECT id FROM transactions WHERE type = 'transfer_in' AND deleted_at IS NULL"
    )
    assert pair is not None
    response = client.put(
        f"/api/transactions/{pair['id']}",
        headers=auth_headers(token),
        json={"amount": 4000},
    )
    assert response.status_code == 200
    assert response.json()["type"] == "transfer"
    assert get_account(client, token, source["id"])["balance"] == 6000
    assert get_account(client, token, target["id"])["balance"] == 4000


def test_patch_missing_transaction(client: TestClient) -> None:
    token = register(client)["token"]
    response = client.put(
        "/api/transactions/not-exists",
        headers=auth_headers(token),
        json={"amount": 100},
    )
    assert response.status_code == 404


def test_patch_other_users_transaction(client: TestClient) -> None:
    alice = register(client, "alice")["token"]
    bob = register(client, "bob")["token"]
    account = create_account(client, alice, initial_balance=10000)
    category = find_category(client, alice, "餐饮", "expense")
    created = create_transaction(
        client,
        alice,
        amount=1000,
        account_id=account["id"],
        category_id=category["id"],
    )
    response = client.put(
        f"/api/transactions/{created['id']}",
        headers=auth_headers(bob),
        json={"amount": 9999},
    )
    assert response.status_code == 404


def test_delete_expense_reverses_balance(client: TestClient, db) -> None:
    token, source, _, expense_category, _ = _setup(client)
    created = create_transaction(
        client,
        token,
        amount=3000,
        account_id=source["id"],
        category_id=expense_category["id"],
    )
    assert get_account(client, token, source["id"])["balance"] == 7000

    response = client.delete(
        f"/api/transactions/{created['id']}", headers=auth_headers(token)
    )
    assert response.status_code == 200
    assert get_account(client, token, source["id"])["balance"] == 10000
    assert list_transactions(client, token)["total"] == 0

    row = db.fetchone(
        "SELECT deleted_at FROM transactions WHERE id = ?", (created["id"],)
    )
    assert row is not None and row["deleted_at"]


def test_delete_income_reverses_balance(client: TestClient) -> None:
    token, source, _, _, income_category = _setup(client)
    created = create_transaction(
        client,
        token,
        tx_type="income",
        amount=3000,
        account_id=source["id"],
        category_id=income_category["id"],
    )
    assert get_account(client, token, source["id"])["balance"] == 13000
    response = client.delete(
        f"/api/transactions/{created['id']}", headers=auth_headers(token)
    )
    assert response.status_code == 200
    assert get_account(client, token, source["id"])["balance"] == 10000


def test_delete_transfer_removes_pair_and_restores_balances(
    client: TestClient, db
) -> None:
    token, source, target, _, _ = _setup(client)
    created = create_transaction(
        client,
        token,
        tx_type="transfer",
        amount=4000,
        account_id=source["id"],
        to_account_id=target["id"],
    )
    assert get_account(client, token, source["id"])["balance"] == 6000
    assert get_account(client, token, target["id"])["balance"] == 4000

    response = client.delete(
        f"/api/transactions/{created['id']}", headers=auth_headers(token)
    )
    assert response.status_code == 200
    assert get_account(client, token, source["id"])["balance"] == 10000
    assert get_account(client, token, target["id"])["balance"] == 0
    assert list_transactions(client, token)["total"] == 0

    rows = db.fetchall("SELECT * FROM transactions")
    assert len(rows) == 2
    assert all(row["deleted_at"] for row in rows)


def test_delete_transfer_by_pair_id(client: TestClient, db) -> None:
    token, source, target, _, _ = _setup(client)
    create_transaction(
        client,
        token,
        tx_type="transfer",
        amount=4000,
        account_id=source["id"],
        to_account_id=target["id"],
    )
    pair = db.fetchone(
        "SELECT id FROM transactions WHERE type = 'transfer_in' AND deleted_at IS NULL"
    )
    assert pair is not None
    response = client.delete(
        f"/api/transactions/{pair['id']}", headers=auth_headers(token)
    )
    assert response.status_code == 200
    assert list_transactions(client, token)["total"] == 0
    assert get_account(client, token, source["id"])["balance"] == 10000
    assert get_account(client, token, target["id"])["balance"] == 0


def test_delete_missing_transaction(client: TestClient) -> None:
    token = register(client)["token"]
    response = client.delete(
        "/api/transactions/not-exists", headers=auth_headers(token)
    )
    assert response.status_code == 404


def test_delete_other_users_transaction(client: TestClient) -> None:
    alice = register(client, "alice")["token"]
    bob = register(client, "bob")["token"]
    account = create_account(client, alice, initial_balance=10000)
    category = find_category(client, alice, "餐饮", "expense")
    created = create_transaction(
        client,
        alice,
        amount=1000,
        account_id=account["id"],
        category_id=category["id"],
    )
    response = client.delete(
        f"/api/transactions/{created['id']}", headers=auth_headers(bob)
    )
    assert response.status_code == 404
    assert list_transactions(client, alice)["total"] == 1


def test_category_kind_mismatch_rejected(client: TestClient) -> None:
    token, source, _, _, income_category = _setup(client)
    response = client.post(
        "/api/transactions",
        headers=auth_headers(token),
        json={
            "type": "expense",
            "amount": 1000,
            "account_id": source["id"],
            "category_id": income_category["id"],
        },
    )
    assert response.status_code == 400


def test_foreign_category_rejected(client: TestClient) -> None:
    alice = register(client, "alice")["token"]
    bob = register(client, "bob")["token"]
    alice_account = create_account(client, alice, initial_balance=10000)
    bob_category = create_category(client, bob, "Bob 分类")
    response = client.post(
        "/api/transactions",
        headers=auth_headers(alice),
        json={
            "type": "expense",
            "amount": 1000,
            "account_id": alice_account["id"],
            "category_id": bob_category["id"],
        },
    )
    assert response.status_code == 404


def test_unknown_account_rejected(client: TestClient) -> None:
    token = register(client)["token"]
    category = find_category(client, token, "餐饮", "expense")
    response = client.post(
        "/api/transactions",
        headers=auth_headers(token),
        json={
            "type": "expense",
            "amount": 1000,
            "account_id": "missing-account",
            "category_id": category["id"],
        },
    )
    assert response.status_code == 404


def test_transactions_are_isolated(client: TestClient) -> None:
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
    )
    assert list_transactions(client, alice)["total"] == 1
    assert list_transactions(client, bob)["total"] == 0


def test_occurred_at_is_preserved(client: TestClient) -> None:
    token, source, _, expense_category, _ = _setup(client)
    created = create_transaction(
        client,
        token,
        amount=1000,
        account_id=source["id"],
        category_id=expense_category["id"],
        occurred_at="2024-05-06",
    )
    assert created["occurred_at"] == "2024-05-06"
    listing = list_transactions(client, token, month="2024-05")
    assert listing["items"][0]["occurred_at"] == "2024-05-06"


def test_amount_must_be_positive(client: TestClient) -> None:
    token, source, _, _, _ = _setup(client)
    response = client.post(
        "/api/transactions",
        headers=auth_headers(token),
        json={"type": "expense", "amount": 0, "account_id": source["id"]},
    )
    assert response.status_code == 422


def test_invalid_occurred_at_is_rejected(client: TestClient) -> None:
    token, source, _, _, _ = _setup(client)
    response = client.post(
        "/api/transactions",
        headers=auth_headers(token),
        json={
            "type": "expense",
            "amount": 1000,
            "account_id": source["id"],
            "occurred_at": "2024-13-99",
        },
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_blank_optional_ids_are_normalized(client: TestClient) -> None:
    token, source, _, expense_category, _ = _setup(client)
    # 前端把“未选择分类”传成空字符串时，应按 NULL 处理而不是触发外键错误
    created = client.post(
        "/api/transactions",
        headers=auth_headers(token),
        json={
            "type": "expense",
            "amount": 1000,
            "account_id": source["id"],
            "category_id": "",
            "to_account_id": "",
        },
    )
    assert created.status_code == 200
    assert created.json()["category_id"] is None
    assert created.json()["to_account_id"] is None

    set_category = client.put(
        f"/api/transactions/{created.json()['id']}",
        headers=auth_headers(token),
        json={"category_id": expense_category["id"]},
    )
    assert set_category.status_code == 200
    assert set_category.json()["category_id"] == expense_category["id"]

    clear = client.put(
        f"/api/transactions/{created.json()['id']}",
        headers=auth_headers(token),
        json={"category_id": ""},
    )
    assert clear.status_code == 200
    assert clear.json()["category_id"] is None
    assert get_account(client, token, source["id"])["balance"] == 9000
