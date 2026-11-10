"""Pydantic 请求模型与字段校验。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"

MAX_AMOUNT = 10**12  # 单笔/预算上限，避免异常大数破坏统计
MAX_NOTE_LENGTH = 500
_OCCURRED_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def normalize_occurred_at(value: str) -> str:
    """校验 ISO8601 日期/日期时间，并保留用户原始写法。

    账本按用户选择的“日期”归类，因此这里不把带时区的时间换算到 UTC，
    避免月初/月末发生时间跨月。
    """

    text = value.strip()
    if not text:
        raise ValueError("occurred_at 不能为空")
    if not _OCCURRED_PREFIX_RE.match(text):
        raise ValueError("occurred_at 需为 YYYY-MM-DD 或 ISO8601 日期时间")

    probe = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        datetime.fromisoformat(probe)
    except ValueError as exc:
        raise ValueError("occurred_at 不是合法的日期时间") from exc
    return text


def _clean_name(value: str, label: str = "名称") -> str:
    text = value.strip()
    if not text:
        raise ValueError(f"{label}不能为空")
    return text


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        return _clean_name(value, "用户名")


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        return _clean_name(value, "用户名")


class DevTokenRequest(BaseModel):
    """调试 token 请求体可省略，默认使用 dango 用户。"""

    username: str = Field(default="dango", min_length=1, max_length=32)

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        return _clean_name(value, "用户名")


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    type: str = Field(default="cash", min_length=1, max_length=20)
    initial_balance: int = Field(default=0, ge=-(10**12), le=10**12)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _clean_name(value, "账户名称")

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: str) -> str:
        return _clean_name(value, "账户类型")


class AccountPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=32)
    initial_balance: int | None = Field(default=None, ge=-(10**12), le=10**12)
    sort: int | None = Field(default=None, ge=-(10**6), le=10**6)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_name(value, "账户名称")


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    kind: Literal["expense", "income"]
    icon: str = Field(default="🍡", max_length=16)
    color: str = Field(default="#FF8A65", max_length=32)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return _clean_name(value, "分类名称")


class TransactionCreate(BaseModel):
    type: Literal["expense", "income", "transfer"]
    amount: int = Field(gt=0, le=MAX_AMOUNT)
    account_id: str = Field(min_length=1, max_length=64)
    to_account_id: str | None = Field(default=None, max_length=64)
    category_id: str | None = Field(default=None, max_length=64)
    occurred_at: str | None = None
    note: str = Field(default="", max_length=MAX_NOTE_LENGTH)

    @field_validator("to_account_id", "category_id", mode="before")
    @classmethod
    def _blank_id_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("occurred_at")
    @classmethod
    def _validate_occurred_at(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_occurred_at(value)

    @field_validator("note")
    @classmethod
    def _clean_note(cls, value: str) -> str:
        return value.strip()


class TransactionPatch(BaseModel):
    amount: int | None = Field(default=None, gt=0, le=MAX_AMOUNT)
    category_id: str | None = Field(default=None, max_length=64)
    occurred_at: str | None = None
    note: str | None = Field(default=None, max_length=MAX_NOTE_LENGTH)

    @field_validator("category_id", mode="before")
    @classmethod
    def _blank_id_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("occurred_at")
    @classmethod
    def _validate_occurred_at(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_occurred_at(value)

    @field_validator("note")
    @classmethod
    def _clean_note(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class BudgetSet(BaseModel):
    month: str = Field(pattern=MONTH_PATTERN)
    amount: int = Field(ge=0, le=MAX_AMOUNT)
