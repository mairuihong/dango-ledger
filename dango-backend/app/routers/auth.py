"""认证接口：注册、登录、当前用户、调试 token。"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import create_access_token, hash_password, verify_password
from ..config import Settings
from ..db import Database, now_iso
from ..deps import get_current_user, get_db, get_settings, unauthorized
from ..schemas import DevTokenRequest, LoginRequest, RegisterRequest

router = APIRouter(prefix="/auth", tags=["认证"])


def _user_public(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "created_at": row["created_at"],
    }


def _token_response(user: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """同时返回 token / access_token，兼容不同前端习惯。"""

    token = create_access_token(user, settings)
    return {
        "token": token,
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.token_expire_minutes * 60,
        "user": _user_public(user),
    }


@router.post("/register", summary="注册")
def register(
    payload: RegisterRequest,
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    existing = db.fetchone(
        "SELECT id FROM users WHERE username = ?",
        (payload.username,),
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已被注册",
        )

    user_id = str(uuid.uuid4())
    timestamp = now_iso()
    try:
        with db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    id, username, password_hash, created_at, updated_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (
                    user_id,
                    payload.username,
                    hash_password(payload.password),
                    timestamp,
                    timestamp,
                ),
            )
    except sqlite3.IntegrityError as exc:
        # 并发注册时由唯一索引兜底
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已被注册",
        ) from exc

    row = db.fetchone(
        "SELECT id, username, created_at FROM users WHERE id = ?",
        (user_id,),
    )
    assert row is not None
    return _token_response(dict(row), settings)


@router.post("/login", summary="登录")
def login(
    payload: LoginRequest,
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    row = db.fetchone(
        """
        SELECT id, username, password_hash, created_at
        FROM users
        WHERE username = ? AND deleted_at IS NULL
        """,
        (payload.username,),
    )
    if row is None or not verify_password(payload.password, row["password_hash"]):
        # 不区分用户不存在与密码错误，避免账号枚举
        raise unauthorized("用户名或密码错误")

    return _token_response(dict(row), settings)


@router.get("/me", summary="当前用户")
def me(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return _user_public(user)


@router.post("/dev-token", summary="调试 token（可通过 DANGO_DEV_TOKEN=0 关闭）")
def dev_token(
    payload: DevTokenRequest | None = None,
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    # 关闭时按规范返回 404，而不是 403，避免暴露调试接口存在
    if not settings.dev_token_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="调试接口已关闭",
        )

    username = payload.username if payload is not None else "dango"
    row = db.fetchone(
        """
        SELECT id, username, created_at
        FROM users
        WHERE username = ? AND deleted_at IS NULL
        """,
        (username,),
    )

    if row is None:
        user_id = str(uuid.uuid4())
        timestamp = now_iso()
        try:
            with db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO users (
                        id, username, password_hash, created_at, updated_at, deleted_at
                    ) VALUES (?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        user_id,
                        username,
                        # 调试用户没有可用密码，随机串占位
                        hash_password(uuid.uuid4().hex),
                        timestamp,
                        timestamp,
                    ),
                )
        except sqlite3.IntegrityError:
            pass

        row = db.fetchone(
            """
            SELECT id, username, created_at
            FROM users
            WHERE username = ? AND deleted_at IS NULL
            """,
            (username,),
        )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="调试用户创建失败",
        )

    return _token_response(dict(row), settings)
