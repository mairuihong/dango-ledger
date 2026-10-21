"""账户接口：列表、新增、修改、墓碑删除、余额重算。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..db import Database, now_iso
from ..deps import get_current_user, get_db
from ..schemas import AccountCreate, AccountPatch

router = APIRouter(prefix="/accounts", tags=["账户"])

_ACCOUNT_COLUMNS = (
    "id, name, type, balance, initial_balance, sort, created_at, updated_at"
)


def account_public(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "balance": row["balance"],
        "initial_balance": row["initial_balance"],
        "sort": row["sort"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def account_list_payload(db: Database, user_id: str) -> dict[str, Any]:
    rows = db.fetchall(
        f"""
        SELECT {_ACCOUNT_COLUMNS}
        FROM accounts
        WHERE user_id = ? AND deleted_at IS NULL
        ORDER BY sort ASC, rowid ASC
        """,
        (user_id,),
    )
    items = [account_public(row) for row in rows]
    return {
        "items": items,
        "total_balance": sum(item["balance"] for item in items),
    }


@router.get("", summary="账户列表 + 总资产")
def list_accounts(
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    return account_list_payload(db, str(user["id"]))


@router.post("", summary="新增账户")
def create_account(
    payload: AccountCreate,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    user_id = str(user["id"])
    account_id = str(uuid.uuid4())
    timestamp = now_iso()

    with db.transaction() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(sort), -1) + 1 AS next_sort
            FROM accounts
            WHERE user_id = ? AND deleted_at IS NULL
            """,
            (user_id,),
        ).fetchone()
        next_sort = int(row["next_sort"])
        conn.execute(
            """
            INSERT INTO accounts (
                id, user_id, name, type, balance, initial_balance, sort,
                created_at, updated_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                account_id,
                user_id,
                payload.name,
                payload.type,
                payload.initial_balance,
                payload.initial_balance,
                next_sort,
                timestamp,
                timestamp,
            ),
        )
        created = conn.execute(
            f"SELECT {_ACCOUNT_COLUMNS} FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()

    assert created is not None
    return account_public(created)


@router.post("/recalc", summary="按流水重算全部账户余额")
def recalc_accounts(
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    user_id = str(user["id"])
    timestamp = now_iso()

    with db.transaction() as conn:
        account_rows = conn.execute(
            """
            SELECT id, initial_balance
            FROM accounts
            WHERE user_id = ? AND deleted_at IS NULL
            """,
            (user_id,),
        ).fetchall()
        balances: dict[str, int] = {
            str(row["id"]): int(row["initial_balance"]) for row in account_rows
        }

        transaction_rows = conn.execute(
            """
            SELECT account_id, to_account_id, amount, type
            FROM transactions
            WHERE user_id = ? AND deleted_at IS NULL
            """,
            (user_id,),
        ).fetchall()

        for tx in transaction_rows:
            tx_type = tx["type"]
            amount = int(tx["amount"])
            account_id = tx["account_id"]
            to_account_id = tx["to_account_id"]

            if tx_type == "expense":
                if account_id in balances:
                    balances[account_id] -= amount
            elif tx_type == "income":
                if account_id in balances:
                    balances[account_id] += amount
            elif tx_type == "transfer":
                # transfer_in 是配对记录，delta 为 0，不在这里重复加减
                if account_id in balances:
                    balances[account_id] -= amount
                if to_account_id in balances:
                    balances[to_account_id] += amount

        for account_id, balance in balances.items():
            conn.execute(
                """
                UPDATE accounts
                SET balance = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (balance, timestamp, account_id, user_id),
            )

    return account_list_payload(db, user_id)


@router.put("/{account_id}", summary="修改账户")
def update_account(
    account_id: str,
    payload: AccountPatch,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    user_id = str(user["id"])
    fields = payload.model_dump(exclude_unset=True)

    with db.transaction() as conn:
        row = conn.execute(
            """
            SELECT *
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

        updates: list[str] = []
        params: list[Any] = []

        if "name" in fields:
            if fields["name"] is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="账户名称不能为空",
                )
            updates.append("name = ?")
            params.append(fields["name"])

        if "initial_balance" in fields:
            if fields["initial_balance"] is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="初始余额不能为空",
                )
            new_initial = int(fields["initial_balance"])
            delta = new_initial - int(row["initial_balance"])
            # 初始余额变化同步调整当前余额，历史流水的 delta 不受影响
            updates.extend(["initial_balance = ?", "balance = balance + ?"])
            params.extend([new_initial, delta])

        if "sort" in fields:
            if fields["sort"] is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="排序值不能为空",
                )
            updates.append("sort = ?")
            params.append(int(fields["sort"]))

        updates.append("updated_at = ?")
        params.append(now_iso())
        params.extend([account_id, user_id])

        conn.execute(
            f"UPDATE accounts SET {', '.join(updates)} "
            "WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            params,
        )
        updated = conn.execute(
            f"SELECT {_ACCOUNT_COLUMNS} FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()

    assert updated is not None
    return account_public(updated)


@router.delete("/{account_id}", summary="删除账户（有流水时拒绝）")
def delete_account(
    account_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    user_id = str(user["id"])

    with db.transaction() as conn:
        row = conn.execute(
            """
            SELECT id
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

        active_count = conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM transactions
            WHERE user_id = ?
              AND deleted_at IS NULL
              AND (account_id = ? OR to_account_id = ?)
            """,
            (user_id, account_id, account_id),
        ).fetchone()["cnt"]
        if int(active_count) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该账户还有流水，请先删除相关流水",
            )

        timestamp = now_iso()
        conn.execute(
            """
            UPDATE accounts
            SET deleted_at = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (timestamp, timestamp, account_id, user_id),
        )

    return {"ok": True, "id": account_id}
