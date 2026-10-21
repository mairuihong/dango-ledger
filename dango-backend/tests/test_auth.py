"""认证与鉴权测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from tests.helpers import auth_headers, login, register


def test_health_is_public(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["name"] == "团子账本"


def test_register_returns_token_and_user(client: TestClient) -> None:
    payload = register(client, "alice", "secret123")
    assert payload["token"]
    assert payload["access_token"] == payload["token"]
    assert payload["token_type"] == "bearer"
    assert payload["user"]["username"] == "alice"
    assert payload["user"]["id"]

    me = client.get("/api/auth/me", headers=auth_headers(payload["token"]))
    assert me.status_code == 200
    assert me.json()["id"] == payload["user"]["id"]


def test_password_is_hashed(client: TestClient, db) -> None:
    register(client, "hash-user", "secret123")
    row = db.fetchone("SELECT password_hash FROM users WHERE username = ?", ("hash-user",))
    assert row is not None
    assert "secret123" not in row["password_hash"]
    assert row["password_hash"].startswith("pbkdf2_sha256$")


def test_duplicate_registration(client: TestClient) -> None:
    register(client, "alice", "secret123")
    response = client.post(
        "/api/auth/register",
        json={"username": "alice", "password": "other123"},
    )
    assert response.status_code == 409
    assert "detail" in response.json()


def test_login_success(client: TestClient) -> None:
    registered = register(client, "alice", "secret123")
    payload = login(client, "alice", "secret123")
    assert payload["user"]["id"] == registered["user"]["id"]
    me = client.get("/api/auth/me", headers=auth_headers(payload["token"]))
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


def test_login_wrong_password(client: TestClient) -> None:
    register(client, "alice", "secret123")
    response = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"]


def test_login_unknown_user(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "nobody", "password": "secret123"},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_requires_token(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_token_is_rejected(client: TestClient) -> None:
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_dev_token_enabled(client: TestClient) -> None:
    response = client.post("/api/auth/dev-token")
    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["username"] == "dango"
    assert payload["token"]

    me = client.get("/api/auth/me", headers=auth_headers(payload["token"]))
    assert me.status_code == 200
    assert me.json()["username"] == "dango"

    # 同一个 dango 用户应复用，不重复建号
    second = client.post(
        "/api/auth/dev-token",
        json={"username": "dango"},
    )
    assert second.status_code == 200
    assert second.json()["user"]["id"] == payload["user"]["id"]


def test_dev_token_disabled_returns_404(tmp_path) -> None:
    application = create_app(
        database_path=tmp_path / "disabled.db",
        dev_token_enabled=False,
    )
    with TestClient(application) as disabled_client:
        response = disabled_client.post("/api/auth/dev-token")
        assert response.status_code == 404
        assert "detail" in response.json()


def test_short_password_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={"username": "short", "password": "123"},
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
