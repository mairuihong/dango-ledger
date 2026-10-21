"""流水接口：增删改查、分页/搜索/月份筛选、转账配对和余额联动。"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..db import (
    SYSTEM_USER_ID,
    Database,
    escape_like,
    local_now_iso,
    month_range,
    now_iso,
)
from ..deps import get_current_user, get_db
from ..schemas import MONTH_PATTERN, TransactionCreate, TransactionPatch

router = APIRouter(prefix="/transactions", tags=["流水"])

# 分类可见性：系统分类 + 当前用户自己的分类
_TX_FROM = """
FROM transactions t
LEFT JOIN accounts a ON a.id = t.account_id
LEFT JOIN accounts ta ON ta.id = t.to_account_id
LEFT JOIN categories c
       ON c.id = t.category_id
      AND (c.user_id = t.user_id OR c.user_id = '__system__')
"""

_TX_COLUMNS = """
t.id, t.type, t.amount, t.account_id, t.to_account_id, t.category_id,
t.occurred_at, t.note, t.created_at, t.updated_at,
a.name AS account_name,
ta.name AS to_account_name,
c.name AS category_name,
c.icon AS category_icon,
c.color AS category_color
"""


def transaction_public(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "type": row["type"],
        "amount": row["amount"],
        "account_id": row["account_id"],
        "account_name": row["account_name"],
        "to_account_id": row["to_account_id"],
        "to_account_name": row["to_account_name"],
        "category_id": row["category_id"],
        "category_name": row["category_name"],
        "category_icon": row["category_icon"],
        "category_color": row["category_color"],
        "occurred_at": row["occurred_at"],
        "note": row["note"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _get_active_transaction(
    conn: sqlite3.Connection, user_id: str, transaction_id: str
) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT *
        FROM transactions
        WHERE id = ? AND user_id = ? AND deleted_at IS NULL
        """,
        (transaction_id, user_id),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="流水不存在",
        )
    return row


def _validate_account(
    conn: sqlite3.Connection, user_id: str, account_id: str
) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT id, name, balance
        FROM accounts
        WHERE id = ? AND user_id = ? AND deleted_at IS NULL
        """,
        (account_id, user_id),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="账户不存在",
        )
    return row


def _validate_category(
    conn: sqlite3.Connection, user_id: str, category_id: str, tx_type: str
) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT id, kind
        FROM categories
        WHERE id = ?
          AND deleted_at IS NULL
          AND (user_id = ? OR user_id = ?)
        """,
        (category_id, user_id, SYSTEM_USER_ID),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="分类不存在",
        )
    if row["kind"] != tx_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="分类类型与流水类型不一致",
        )
    return row


def _change_balance(
    conn: sqlite3.Connection, account_id: str, delta: int, timestamp: str
) -> None:
    """在事务内更新账户余额；账户必须存在且未删除。"""

    cursor = conn.execute(
        """
        UPDATE accounts
        SET balance = balance + ?, updated_at = ?
        WHERE id = ? AND deleted_at IS NULL
        """,
        (delta, timestamp, account_id),
    )
    if cursor.rowcount == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="账户不存在或已删除，无法更新余额",
        )


def _find_transfer_pair(
    conn: sqlite3.Connection, user_id: str, tx: sqlite3.Row
) -> sqlite3.Row | None:
    """按“account_id/to_account_id 互换 + type=transfer_in + 未删除”找配对。"""

    if tx["type"] == "transfer":
        pair_type = "transfer_in"
        account_id = tx["to_account_id"]
        to_account_id = tx["account_id"]
    elif tx["type"] == "transfer_in":
        pair_type = "transfer"
        account_id = tx["to_account_id"]
        to_account_id = tx["account_id"]
    else:
        return None

    if not account_id or not to_account_id:
        return None

    return conn.execute(
        """
        SELECT *
        FROM transactions
        WHERE user_id = ?
          AND type = ?
          AND account_id = ?
          AND to_account_id = ?
          AND deleted_at IS NULL
          AND id <> ?
        ORDER BY
            CASE WHEN amount = ? THEN 0 ELSE 1 END,
            CASE WHEN occurred_at = ? THEN 0 ELSE 1 END,
            created_at ASC,
            rowid ASC
        LIMIT 1
        """,
        (
            user_id,
            pair_type,
            account_id,
            to_account_id,
            tx["id"],
            tx["amount"],
            tx["occurred_at"],
        ),
    ).fetchone()


def _fetch_joined(
    db: Database, user_id: str, transaction_id: str
) -> dict[str, Any] | None:
    row = db.fetchone(
        f"""
        SELECT {_TX_COLUMNS}
        {_TX_FROM}
        WHERE t.id = ? AND t.user_id = ? AND t.deleted_at IS NULL
        """,
        (transaction_id, user_id),
    )
    return transaction_public(row) if row is not None else None


@router.get("", summary="流水列表（月份 / 关键字 / 分页）")
def list_transactions(
    month: str | None = Query(default=None, pattern=MONTH_PATTERN),
    keyword: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    user_id = str(user["id"])
    conditions = ["t.user_id = ?", "t.deleted_at IS NULL", "t.type <> 'transfer_in'"]
    params: list[Any] = [user_id]

    if month:
        start, end = month_range(month)
        conditions.append("t.occurred_at >= ? AND t.occurred_at < ?")
        params.extend([start, end])

    cleaned_keyword = (keyword or "").strip()
    if cleaned_keyword:
        pattern = f"%{escape_like(cleaned_keyword)}%"
        conditions.append(
            "(t.note LIKE ? ESCAPE '\\' OR c.name LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern, pattern])

    where_sql = " AND ".join(conditions)
    total = db.scalar(
        f"SELECT COUNT(*) {_TX_FROM} WHERE {where_sql}",
        params,
    )

    offset = (page - 1) * page_size
    rows = db.fetchall(
        f"""
        SELECT {_TX_COLUMNS}
        {_TX_FROM}
        WHERE {where_sql}
        ORDER BY t.occurred_at DESC, t.created_at DESC, t.rowid DESC
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, offset],
    )

    return {
        "items": [transaction_public(row) for row in rows],
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
    }


@router.post("", summary="新增流水（转账自动配对）")
def create_transaction(
    payload: TransactionCreate,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    user_id = str(user["id"])
    transaction_id = str(uuid.uuid4())
    timestamp = now_iso()
    occurred_at = payload.occurred_at or local_now_iso()

    with db.transaction() as conn:
        # 转出/支出/收入账户必须属于当前用户
        _validate_account(conn, user_id, payload.account_id)

        if payload.type == "transfer":
            if not payload.to_account_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="转账必须指定转入账户",
                )
            if payload.to_account_id == payload.account_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="转出账户和转入账户不能相同",
                )
            _validate_account(conn, user_id, payload.to_account_id)

            pair_id = str(uuid.uuid4())
            # 转出记录
            conn.execute(
                """
                INSERT INTO transactions (
                    id, user_id, account_id, to_account_id, category_id,
                    amount, type, occurred_at, note,
                    created_at, updated_at, deleted_at
                ) VALUES (?, ?, ?, ?, NULL, ?, 'transfer', ?, ?, ?, ?, NULL)
                """,
                (
                    transaction_id,
                    user_id,
                    payload.account_id,
                    payload.to_account_id,
                    payload.amount,
                    occurred_at,
                    payload.note,
                    timestamp,
                    timestamp,
                ),
            )
            # 转入配对记录：account_id / to_account_id 与转出记录互换
            conn.execute(
                """
                INSERT INTO transactions (
                    id, user_id, account_id, to_account_id, category_id,
                    amount, type, occurred_at, note,
                    created_at, updated_at, deleted_at
                ) VALUES (?, ?, ?, ?, NULL, ?, 'transfer_in', ?, ?, ?, ?, NULL)
                """,
                (
                    pair_id,
                    user_id,
                    payload.to_account_id,
                    payload.account_id,
                    payload.amount,
                    occurred_at,
                    payload.note,
                    timestamp,
                    timestamp,
                ),
            )
            _change_balance(conn, payload.account_id, -payload.amount, timestamp)
            _change_balance(conn, payload.to_account_id, payload.amount, timestamp)
        else:
            if payload.to_account_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="只有转账可以指定转入账户",
                )
            if payload.category_id:
                _validate_category(conn, user_id, payload.category_id, payload.type)

            conn.execute(
                """
                INSERT INTO transactions (
                    id, user_id, account_id, to_account_id, category_id,
                    amount, type, occurred_at, note,
                    created_at, updated_at, deleted_at
                ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    transaction_id,
                    user_id,
                    payload.account_id,
                    payload.category_id,
                    payload.amount,
                    payload.type,
                    occurred_at,
                    payload.note,
                    timestamp,
                    timestamp,
                ),
            )
            delta = -payload.amount if payload.type == "expense" else payload.amount
            _change_balance(conn, payload.account_id, delta, timestamp)

    created = _fetch_joined(db, user_id, transaction_id)
    assert created is not None
    return created


@router.put("/{transaction_id}", summary="编辑流水（先回滚旧 delta 再应用新 delta）")
def update_transaction(
    transaction_id: str,
    payload: TransactionPatch,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    user_id = str(user["id"])
    fields = payload.model_dump(exclude_unset=True)
    timestamp = now_iso()

    with db.transaction() as conn:
        row = _get_active_transaction(conn, user_id, transaction_id)

        if row["type"] in ("transfer", "transfer_in"):
            pair = _find_transfer_pair(conn, user_id, row)
            if pair is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="转账配对记录缺失，无法修改",
                )
            # 统一以 type=transfer 的记录为主记录
            primary = row if row["type"] == "transfer" else pair
            mirror = pair if row["type"] == "transfer" else row

            new_amount = (
                int(fields["amount"])
                if "amount" in fields and fields["amount"] is not None
                else int(primary["amount"])
            )
            new_occurred_at = (
                fields["occurred_at"]
                if "occurred_at" in fields and fields["occurred_at"] is not None
                else primary["occurred_at"]
            )
            new_note = (
                (fields["note"] or "")
                if "note" in fields
                else primary["note"]
            )

            old_amount = int(primary["amount"])
            # 旧 delta：转出 -old、转入 +old；新 delta：转出 -new、转入 +new
            _change_balance(
                conn, primary["account_id"], old_amount - new_amount, timestamp
            )
            _change_balance(
                conn, primary["to_account_id"], new_amount - old_amount, timestamp
            )

            conn.execute(
                """
                UPDATE transactions
                SET amount = ?, occurred_at = ?, note = ?, updated_at = ?
                WHERE id IN (?, ?) AND user_id = ? AND deleted_at IS NULL
                """,
                (
                    new_amount,
                    new_occurred_at,
                    new_note,
                    timestamp,
                    primary["id"],
                    mirror["id"],
                    user_id,
                ),
            )
            result_id = str(primary["id"])
        else:
            new_amount = (
                int(fields["amount"])
                if "amount" in fields and fields["amount"] is not None
                else int(row["amount"])
            )
            if "category_id" in fields:
                new_category_id = fields["category_id"]
                if new_category_id:
                    _validate_category(conn, user_id, new_category_id, row["type"])
            else:
                new_category_id = row["category_id"]

            new_occurred_at = (
                fields["occurred_at"]
                if "occurred_at" in fields and fields["occurred_at"] is not None
                else row["occurred_at"]
            )
            new_note = (
                (fields["note"] or "") if "note" in fields else row["note"]
            )

            old_amount = int(row["amount"])
            if row["type"] == "expense":
                delta = -new_amount - (-old_amount)
            else:
                delta = new_amount - old_amount
            _change_balance(conn, row["account_id"], delta, timestamp)

            conn.execute(
                """
                UPDATE transactions
                SET amount = ?, category_id = ?, occurred_at = ?, note = ?,
                    updated_at = ?
                WHERE id = ? AND user_id = ? AND deleted_at IS NULL
                """,
                (
                    new_amount,
                    new_category_id,
                    new_occurred_at,
                    new_note,
                    timestamp,
                    transaction_id,
                    user_id,
                ),
            )
            result_id = transaction_id

    updated = _fetch_joined(db, user_id, result_id)
    assert updated is not None
    return updated


@router.delete("/{transaction_id}", summary="删除流水（墓碑 + 反向冲销）")
def delete_transaction(
    transaction_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    user_id = str(user["id"])
    timestamp = now_iso()

    with db.transaction() as conn:
        row = _get_active_transaction(conn, user_id, transaction_id)

        if row["type"] in ("transfer", "transfer_in"):
            pair = _find_transfer_pair(conn, user_id, row)
            if pair is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="转账配对记录缺失，无法删除",
                )
            primary = row if row["type"] == "transfer" else pair

            # 反向冲销：转出账户加回，转入账户扣回
            _change_balance(
                conn, primary["account_id"], int(primary["amount"]), timestamp
            )
            _change_balance(
                conn, primary["to_account_id"], -int(primary["amount"]), timestamp
            )
            conn.execute(
                """
                UPDATE transactions
                SET deleted_at = ?, updated_at = ?
                WHERE id IN (?, ?) AND user_id = ? AND deleted_at IS NULL
                """,
                (
                    timestamp,
                    timestamp,
                    row["id"],
                    pair["id"],
                    user_id,
                ),
            )
        else:
            # 反向 delta：支出把钱加回，收入把钱扣回
            reverse = (
                int(row["amount"])
                if row["type"] == "expense"
                else -int(row["amount"])
            )
            _change_balance(conn, row["account_id"], reverse, timestamp)
            conn.execute(
                """
                UPDATE transactions
                SET deleted_at = ?, updated_at = ?
                WHERE id = ? AND user_id = ? AND deleted_at IS NULL
                """,
                (timestamp, timestamp, transaction_id, user_id),
            )

    return {"ok": True, "id": transaction_id}
