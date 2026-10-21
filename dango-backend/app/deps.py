"""FastAPI 公共依赖：数据库、配置、当前登录用户。"""

from __future__ import annotations

from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth import decode_access_token
from .config import Settings
from .db import Database

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Authorization: Bearer <token>",
)


def unauthorized(detail: str = "未登录或登录已过期") -> HTTPException:
    """统一的 401；按规范带 WWW-Authenticate: Bearer。"""

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """从 Bearer token 取用户；无效/过期/已删除都返回 401。"""

    if credentials is None or not credentials.credentials:
        raise unauthorized()

    try:
        payload = decode_access_token(credentials.credentials, settings)
    except jwt.ExpiredSignatureError as exc:
        raise unauthorized("登录已过期，请重新登录") from exc
    except jwt.InvalidTokenError as exc:
        raise unauthorized("无效的登录凭证") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise unauthorized()

    row = db.fetchone(
        """
        SELECT id, username, created_at
        FROM users
        WHERE id = ? AND deleted_at IS NULL
        """,
        (user_id,),
    )
    if row is None:
        raise unauthorized("用户不存在或已注销")

    return dict(row)


def get_current_user_id(user: dict[str, Any] = Depends(get_current_user)) -> str:
    return str(user["id"])
