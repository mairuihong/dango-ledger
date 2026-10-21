"""团子账本 · Dango Ledger 启动脚本。

用法：
    python run.py
或：
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import uvicorn

from app.config import Settings


def main() -> None:
    settings = Settings.from_env()
    display_host = "127.0.0.1" if settings.host in ("0.0.0.0", "::") else settings.host
    print("团子账本 · Dango Ledger 后端")
    print(f"   接口文档: http://{display_host}:{settings.port}/docs")
    print(f"   健康检查: http://{display_host}:{settings.port}/api/health")
    print(f"   SQLite:   {settings.database_path}")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
