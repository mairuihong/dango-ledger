"""月度预算接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..db import Database, current_month, now_iso
from ..deps import get_current_user, get_db
from ..schemas import MONTH_PATTERN, BudgetSet

router = APIRouter(prefix="/budgets", tags=["预算"])


@router.get("", summary="读取月度预算")
def get_budget(
    month: str | None = Query(default=None, pattern=MONTH_PATTERN),
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    user_id = str(user["id"])
    target_month = month or current_month()
    row = db.fetchone(
        """
        SELECT month, amount
        FROM budgets
        WHERE user_id = ? AND month = ?
        """,
        (user_id, target_month),
    )
    return {
        "month": target_month,
        "amount": int(row["amount"]) if row is not None else 0,
    }


@router.put("", summary="设置月度预算（upsert）")
def set_budget(
    payload: BudgetSet,
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    user_id = str(user["id"])
    with db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO budgets (user_id, month, amount, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, month)
            DO UPDATE SET amount = excluded.amount, updated_at = excluded.updated_at
            """,
            (user_id, payload.month, payload.amount, now_iso()),
        )
    return {"month": payload.month, "amount": payload.amount}
