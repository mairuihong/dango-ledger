"""分类接口：系统分类只读，自定义分类可增删。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..db import SYSTEM_USER_ID, Database, now_iso
from ..deps import get_current_user, get_db
from ..schemas import CategoryCreate

router = APIRouter(prefix="/categories", tags=["分类"])


def category_public(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "icon": row["icon"],
        "color": row["color"],
        "sort": row["sort"],
        "is_system": row["user_id"] == SYSTEM_USER_ID,
    }


@router.get("", summary="分类列表（系统分类 + 当前用户分类）")
def list_categories(
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> list[dict[str, Any]]:
    user_id = str(user["id"])
    rows = db.fetchall(
        """
        SELECT id, user_id, name, kind, icon, color, sort
        FROM categories
        WHERE deleted_at IS NULL
          AND (user_id = ? OR user_id = ?)
        ORDER BY kind ASC, sort ASC, rowid ASC
        """,
        (user_id, SYSTEM_USER_ID),
    )
    return [category_public(row) for row in rows]


@router.post("", summary="新增自定义分类")
def create_category(
    payload: CategoryCreate,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    user_id = str(user["id"])
    category_id = str(uuid.uuid4())
    timestamp = now_iso()

    with db.transaction() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM categories
            WHERE user_id = ?
              AND kind = ?
              AND name = ?
              AND deleted_at IS NULL
            """,
            (user_id, payload.kind, payload.name),
        ).fetchone()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="同类型下已存在同名分类",
            )

        row = conn.execute(
            """
            SELECT COALESCE(MAX(sort), -1) + 10 AS next_sort
            FROM categories
            WHERE deleted_at IS NULL
              AND (user_id = ? OR user_id = ?)
              AND kind = ?
            """,
            (user_id, SYSTEM_USER_ID, payload.kind),
        ).fetchone()
        next_sort = int(row["next_sort"])

        conn.execute(
            """
            INSERT INTO categories (
                id, user_id, name, kind, icon, color, parent_id, sort,
                created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL)
            """,
            (
                category_id,
                user_id,
                payload.name,
                payload.kind,
                payload.icon,
                payload.color,
                next_sort,
                timestamp,
                timestamp,
            ),
        )
        created = conn.execute(
            """
            SELECT id, user_id, name, kind, icon, color, sort
            FROM categories
            WHERE id = ?
            """,
            (category_id,),
        ).fetchone()

    assert created is not None
    return category_public(created)


@router.delete("/{category_id}", summary="删除自定义分类（系统分类 403）")
def delete_category(
    category_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    user_id = str(user["id"])

    with db.transaction() as conn:
        row = conn.execute(
            """
            SELECT id, user_id
            FROM categories
            WHERE id = ? AND deleted_at IS NULL
            """,
            (category_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="分类不存在",
            )
        if row["user_id"] == SYSTEM_USER_ID:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="系统分类只读，不能删除",
            )
        if row["user_id"] != user_id:
            # 不向其他用户暴露该分类是否存在
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="分类不存在",
            )

        timestamp = now_iso()
        conn.execute(
            """
            UPDATE categories
            SET deleted_at = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (timestamp, timestamp, category_id, user_id),
        )

    return {"ok": True, "id": category_id}
