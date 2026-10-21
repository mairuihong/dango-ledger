"""统计接口：月度概览、分类占比、每日趋势、近 N 月趋势。

口径：只统计 type in ('income', 'expense') 且 deleted_at is null 的流水；
转账（transfer / transfer_in）不计入收入或支出。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..db import Database, current_month, month_range, shift_month
from ..deps import get_current_user, get_db
from ..schemas import MONTH_PATTERN

router = APIRouter(prefix="/stats", tags=["统计"])

_STATS_FILTER = """
    t.user_id = ?
    AND t.deleted_at IS NULL
    AND t.type IN ('income', 'expense')
    AND t.occurred_at >= ?
    AND t.occurred_at < ?
"""


@router.get("/overview", summary="月度概览")
def overview(
    month: str | None = Query(default=None, pattern=MONTH_PATTERN),
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    user_id = str(user["id"])
    target_month = month or current_month()
    start, end = month_range(target_month)
    params = (user_id, start, end)

    summary = db.fetchone(
        f"""
        SELECT
            COALESCE(SUM(CASE WHEN t.type = 'income' THEN t.amount ELSE 0 END), 0)
                AS income,
            COALESCE(SUM(CASE WHEN t.type = 'expense' THEN t.amount ELSE 0 END), 0)
                AS expense,
            COUNT(*) AS transaction_count
        FROM transactions t
        WHERE {_STATS_FILTER}
        """,
        params,
    )
    income = int(summary["income"]) if summary is not None else 0
    expense = int(summary["expense"]) if summary is not None else 0
    transaction_count = int(summary["transaction_count"]) if summary is not None else 0

    category_rows = db.fetchall(
        f"""
        SELECT
            t.category_id AS category_id,
            c.name AS name,
            c.icon AS icon,
            c.color AS color,
            SUM(t.amount) AS amount,
            COUNT(*) AS count
        FROM transactions t
        LEFT JOIN categories c
               ON c.id = t.category_id
              AND (c.user_id = t.user_id OR c.user_id = '__system__')
        WHERE {_STATS_FILTER}
          AND t.type = 'expense'
        GROUP BY t.category_id
        ORDER BY amount DESC, name ASC
        """,
        params,
    )

    categories: list[dict[str, Any]] = []
    for row in category_rows:
        amount = int(row["amount"])
        percent = round(amount * 100 / expense, 2) if expense > 0 else 0.0
        categories.append(
            {
                "category_id": row["category_id"],
                "name": row["name"] or "未分类",
                "icon": row["icon"] or "❓",
                "color": row["color"] or "#9E9E9E",
                "amount": amount,
                "percent": percent,
                "count": int(row["count"]),
            }
        )

    daily_rows = db.fetchall(
        f"""
        SELECT
            substr(t.occurred_at, 1, 10) AS date,
            COALESCE(SUM(CASE WHEN t.type = 'income' THEN t.amount ELSE 0 END), 0)
                AS income,
            COALESCE(SUM(CASE WHEN t.type = 'expense' THEN t.amount ELSE 0 END), 0)
                AS expense
        FROM transactions t
        WHERE {_STATS_FILTER}
        GROUP BY substr(t.occurred_at, 1, 10)
        ORDER BY date ASC
        """,
        params,
    )

    daily: list[dict[str, Any]] = []
    for row in daily_rows:
        day_income = int(row["income"])
        day_expense = int(row["expense"])
        daily.append(
            {
                "date": row["date"],
                "income": day_income,
                "expense": day_expense,
                "balance": day_income - day_expense,
            }
        )

    return {
        "month": target_month,
        "income": income,
        "expense": expense,
        "balance": income - expense,
        "transaction_count": transaction_count,
        "categories": categories,
        "daily": daily,
    }


@router.get("/monthly-trend", summary="近 N 月收支趋势")
def monthly_trend(
    months: int = Query(default=6, ge=1, le=36),
    user: dict[str, Any] = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict[str, Any]:
    user_id = str(user["id"])
    end_month = current_month()
    start_month = shift_month(end_month, -(months - 1))

    start = f"{start_month}-01"
    end = f"{shift_month(end_month, 1)}-01"

    rows = db.fetchall(
        """
        SELECT
            substr(t.occurred_at, 1, 7) AS month,
            COALESCE(SUM(CASE WHEN t.type = 'income' THEN t.amount ELSE 0 END), 0)
                AS income,
            COALESCE(SUM(CASE WHEN t.type = 'expense' THEN t.amount ELSE 0 END), 0)
                AS expense
        FROM transactions t
        WHERE t.user_id = ?
          AND t.deleted_at IS NULL
          AND t.type IN ('income', 'expense')
          AND t.occurred_at >= ?
          AND t.occurred_at < ?
        GROUP BY substr(t.occurred_at, 1, 7)
        ORDER BY month ASC
        """,
        (user_id, start, end),
    )
    by_month = {row["month"]: row for row in rows}

    items: list[dict[str, Any]] = []
    for index in range(months):
        month_key = shift_month(start_month, index)
        row = by_month.get(month_key)
        month_income = int(row["income"]) if row is not None else 0
        month_expense = int(row["expense"]) if row is not None else 0
        items.append(
            {
                "month": month_key,
                "income": month_income,
                "expense": month_expense,
                "balance": month_income - month_expense,
            }
        )

    return {
        "months": months,
        "start_month": start_month,
        "end_month": end_month,
        "items": items,
    }
