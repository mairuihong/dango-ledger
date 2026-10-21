"""团子账本 · Dango Ledger FastAPI 应用入口。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import BASE_DIR, Settings
from .db import Database
from .routers import accounts, auth, budgets, categories, stats, transactions
from .seed import seed_system_categories


def _resolve_path(path: str | Path) -> Path:
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        resolved = (BASE_DIR / resolved).resolve()
    return resolved


def create_app(
    settings: Settings | None = None,
    *,
    database_path: str | Path | None = None,
    dev_token_enabled: bool | None = None,
) -> FastAPI:
    """创建应用；测试可传入独立的临时 SQLite 路径。"""

    current = settings or Settings.from_env()
    if database_path is not None:
        current = replace(current, database_path=_resolve_path(database_path))
    if dev_token_enabled is not None:
        current = replace(current, dev_token_enabled=dev_token_enabled)

    database = Database(current.database_path)
    database.initialize()
    seed_system_categories(database)

    application = FastAPI(
        title=current.app_name,
        version=current.version,
        description=(
            "团子账本（Dango Ledger）在线账本后端："
            "认证、账户、分类、流水、预算与统计。所有金额单位均为「分」。"
        ),
    )
    application.state.settings = current
    application.state.db = database

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(current.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/api/health", tags=["系统"], summary="健康检查")
    def health() -> dict[str, Any]:
        database.fetchone("SELECT 1")
        return {
            "status": "ok",
            "name": "团子账本",
            "version": current.version,
        }

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """把 Pydantic 校验错误统一成 {detail: "..."}，同时保留 errors 明细。"""

        errors = exc.errors()
        detail = "请求参数不合法"
        if errors:
            first = errors[0]
            location = ".".join(
                str(part)
                for part in first.get("loc", ())
                if part not in ("body", "query", "path")
            )
            message = first.get("msg", "参数不合法")
            detail = f"参数校验失败：{location + ' ' if location else ''}{message}"
        return JSONResponse(
            status_code=422,
            content={
                "detail": detail,
                "errors": jsonable_encoder(errors),
            },
        )

    application.include_router(auth.router, prefix="/api")
    application.include_router(accounts.router, prefix="/api")
    application.include_router(categories.router, prefix="/api")
    application.include_router(transactions.router, prefix="/api")
    application.include_router(budgets.router, prefix="/api")
    application.include_router(stats.router, prefix="/api")

    return application


app = create_app()
