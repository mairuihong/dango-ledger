"""分类接口测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.helpers import (
    auth_headers,
    create_category,
    find_category,
    list_categories,
    register,
)


def test_category_list_contains_system_categories(client: TestClient) -> None:
    token = register(client)["token"]
    categories = list_categories(client, token)
    assert categories
    assert all(item["is_system"] is True for item in categories)
    assert {item["kind"] for item in categories} == {"expense", "income"}
    system_names = {item["name"] for item in categories}
    assert {"餐饮", "交通", "工资"} <= system_names


def test_category_list_sorted_by_kind_and_sort(client: TestClient) -> None:
    token = register(client)["token"]
    categories = list_categories(client, token)
    keys = [(item["kind"], item["sort"]) for item in categories]
    assert keys == sorted(keys)


def test_create_custom_category(client: TestClient) -> None:
    token = register(client)["token"]
    created = create_category(client, token, "咖啡", "expense", "☕", "#795548")
    assert created["name"] == "咖啡"
    assert created["kind"] == "expense"
    assert created["icon"] == "☕"
    assert created["color"] == "#795548"
    assert created["is_system"] is False
    assert created["sort"] > 90  # 排在该类型系统分类之后

    categories = list_categories(client, token)
    assert find_category(client, token, "咖啡", "expense")["id"] == created["id"]
    keys = [(item["kind"], item["sort"]) for item in categories]
    assert keys == sorted(keys)


def test_delete_custom_category_tombstone(client: TestClient, db) -> None:
    token = register(client)["token"]
    category = create_category(client, token, "临时分类")
    response = client.delete(
        f"/api/categories/{category['id']}", headers=auth_headers(token)
    )
    assert response.status_code == 200
    assert all(item["id"] != category["id"] for item in list_categories(client, token))

    row = db.fetchone(
        "SELECT deleted_at FROM categories WHERE id = ?", (category["id"],)
    )
    assert row is not None and row["deleted_at"]


def test_system_category_cannot_be_deleted(client: TestClient) -> None:
    token = register(client)["token"]
    category = find_category(client, token, "餐饮", "expense")
    response = client.delete(
        f"/api/categories/{category['id']}", headers=auth_headers(token)
    )
    assert response.status_code == 403
    assert "系统分类" in response.json()["detail"]


def test_custom_categories_are_isolated(client: TestClient) -> None:
    alice = register(client, "alice")["token"]
    bob = register(client, "bob")["token"]
    category = create_category(client, alice, "Alice 专属")

    bob_categories = list_categories(client, bob)
    assert all(item["id"] != category["id"] for item in bob_categories)

    delete = client.delete(
        f"/api/categories/{category['id']}", headers=auth_headers(bob)
    )
    assert delete.status_code == 404

    assert find_category(client, alice, "Alice 专属")["id"] == category["id"]


def test_category_kind_validation(client: TestClient) -> None:
    token = register(client)["token"]
    response = client.post(
        "/api/categories",
        headers=auth_headers(token),
        json={"name": "错误类型", "kind": "unknown", "icon": "x", "color": "#000000"},
    )
    assert response.status_code == 422


def test_duplicate_custom_category_rejected(client: TestClient) -> None:
    token = register(client)["token"]
    create_category(client, token, "重复")
    response = client.post(
        "/api/categories",
        headers=auth_headers(token),
        json={"name": "重复", "kind": "expense", "icon": "x", "color": "#000000"},
    )
    assert response.status_code == 409


def test_category_requires_auth(client: TestClient) -> None:
    response = client.get("/api/categories")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
