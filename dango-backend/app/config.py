"""团子账本 · Dango Ledger 配置。

配置优先级：真实环境变量 > 当前目录下的 .env > 代码默认值。
不引入 python-dotenv，保持依赖精简。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# dango-backend/ 目录：app/config.py 的上一级
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


def _load_dotenv(path: Path = ENV_FILE) -> None:
    """读取简单的 KEY=VALUE 格式 .env 文件，不覆盖已存在的环境变量。"""

    if not path.is_file():
        return

    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        # 去掉成对的引号
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _env_bool(name: str, default: bool) -> bool:
    """把 0/1、true/false、yes/no 等写法解析为布尔值。"""

    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", "none", ""}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


def _resolve_database_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    return path


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    """运行期配置快照。

    测试可以通过 create_app(database_path=...) 覆盖数据库路径，避免污染正式库。
    """

    database_path: Path
    jwt_secret: str = "dango-ledger-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    token_expire_minutes: int = 60 * 24 * 7
    dev_token_enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    cors_origins: tuple[str, ...] = ("*",)
    app_name: str = "团子账本 · Dango Ledger"
    version: str = "1.0.0"

    @classmethod
    def from_env(cls) -> Settings:
        database_raw = os.getenv("DANGO_DATABASE") or os.getenv("DANGO_DB") or "./data/dango.db"
        database_path = _resolve_database_path(database_raw.strip() or "./data/dango.db")

        # 同时兼容 DANGO_JWT_SECRET 与旧名 DANGO_SECRET_KEY
        jwt_secret = (
            os.getenv("DANGO_JWT_SECRET")
            or os.getenv("DANGO_SECRET_KEY")
            or "dango-ledger-dev-secret-change-me"
        )

        origins_raw = os.getenv("DANGO_CORS_ORIGINS") or os.getenv("DANGO_CORS") or "*"
        cors_origins = tuple(
            origin.strip() for origin in origins_raw.split(",") if origin.strip()
        ) or ("*",)

        port = _env_int("DANGO_PORT", 8000)
        if not 1 <= port <= 65535:
            port = 8000

        expire_minutes = _env_int("DANGO_TOKEN_EXPIRE_MINUTES", 0)
        if expire_minutes <= 0:
            # 兼容旧配置 DANGO_JWT_HOURS
            expire_hours = _env_int("DANGO_JWT_HOURS", 0)
            expire_minutes = expire_hours * 60 if expire_hours > 0 else 60 * 24 * 7

        return cls(
            database_path=database_path,
            jwt_secret=jwt_secret,
            token_expire_minutes=expire_minutes,
            dev_token_enabled=_env_bool("DANGO_DEV_TOKEN", True),
            host=os.getenv("DANGO_HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=port,
            reload=_env_bool("DANGO_RELOAD", False),
            cors_origins=cors_origins,
        )
