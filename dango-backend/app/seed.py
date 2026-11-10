"""系统分类种子数据。

系统分类 user_id 固定为 '__system__'，所有用户只读。
分类 id 用 UUIDv5 生成，保证每次建库/重启后保持一致。
"""

from __future__ import annotations

import uuid

from .db import SYSTEM_USER_ID, Database, now_iso

# 固定命名空间，只用于生成稳定的系统分类 id
_SYSTEM_NAMESPACE = uuid.UUID("3c1f5c2e-9a8b-4f6d-8e7a-1b2c3d4e5f60")

# (名称, 类型, emoji, 颜色, 排序)
SYSTEM_CATEGORIES: tuple[tuple[str, str, str, str, int], ...] = (
    ("餐饮", "expense", "🍜", "#FF8A65", 10),
    ("交通", "expense", "🚌", "#42A5F5", 20),
    ("购物", "expense", "🛍️", "#AB47BC", 30),
    ("居住", "expense", "🏠", "#8D6E63", 40),
    ("娱乐", "expense", "🎮", "#FFCA28", 50),
    ("医疗", "expense", "💊", "#EF5350", 60),
    ("教育", "expense", "📚", "#26A69A", 70),
    ("人情", "expense", "🎁", "#EC407A", 80),
    ("其他", "expense", "📦", "#9E9E9E", 90),
    ("宠物", "expense", "🐱", "#FF8A65", 100),
    ("旅行", "expense", "✈️", "#26C6DA", 110),
    ("数码", "expense", "📱", "#5C6BC0", 120),
    ("服饰", "expense", "👕", "#EC407A", 130),
    ("运动", "expense", "⚽", "#66BB6A", 140),
    ("咖啡", "expense", "☕", "#8D6E63", 150),
    ("零食", "expense", "🍪", "#FFA726", 160),
    ("通讯", "expense", "📶", "#42A5F5", 170),
    ("保险", "expense", "🛡️", "#78909C", 180),
    ("汽车", "expense", "🚗", "#EF5350", 190),
    ("母婴", "expense", "🍼", "#F06292", 200),
    ("捐赠", "expense", "🤝", "#26A69A", 210),
    ("工资", "income", "💰", "#66BB6A", 10),
    ("奖金", "income", "🏆", "#FFA726", 20),
    ("理财", "income", "📈", "#29B6F6", 30),
    ("兼职", "income", "💼", "#5C6BC0", 40),
    ("其他收入", "income", "✨", "#9E9E9E", 50),
    ("红包", "income", "🧧", "#EF5350", 60),
    ("报销", "income", "🧾", "#42A5F5", 70),
    ("退款", "income", "↩️", "#26A69A", 80),
    ("利息", "income", "🏦", "#66BB6A", 90),
    ("租金", "income", "🏠", "#8D6E63", 100),
    ("稿费", "income", "✍️", "#AB47BC", 110),
)


def system_category_id(kind: str, name: str) -> str:
    return str(uuid.uuid5(_SYSTEM_NAMESPACE, f"dango:{kind}:{name}"))


def seed_system_categories(db: Database) -> None:
    """幂等写入系统分类；已存在的 id 不覆盖。"""

    timestamp = now_iso()
    with db.transaction() as conn:
        for name, kind, icon, color, sort in SYSTEM_CATEGORIES:
            conn.execute(
                """
                INSERT OR IGNORE INTO categories (
                    id, user_id, name, kind, icon, color, parent_id, sort,
                    created_at, updated_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL)
                """,
                (
                    system_category_id(kind, name),
                    SYSTEM_USER_ID,
                    name,
                    kind,
                    icon,
                    color,
                    sort,
                    timestamp,
                    timestamp,
                ),
            )
