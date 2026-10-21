# 团子账本 · Dango Ledger 后端

在线账本后端：FastAPI + SQLite，所有数据以 HTTP 接口为准，前端不做本地存储，也没有 push/pull 同步协议。

- 品牌：团子账本 / Dango Ledger
- 金额：整数「分」
- 主键：服务端生成的 UUID
- 删除：写 `deleted_at` 墓碑，不做物理删除
- 用户隔离：所有业务接口从 Bearer token 取用户，按 `user_id` 隔离；系统分类只读

## 技术栈

| 层 | 选型 |
|---|---|
| 运行时 | Python 3.10+（本机测试 3.12） |
| Web | FastAPI + Uvicorn |
| 数据库 | 标准库 `sqlite3`，不用 ORM；WAL、`foreign_keys=ON`、`synchronous=NORMAL` |
| 认证 | PyJWT（HS256）+ `hashlib.pbkdf2_hmac` |
| 校验 | Pydantic v2 |
| 测试 | pytest + FastAPI TestClient + 临时 SQLite |

## 目录结构

```
dango-backend/
├── run.py                 # python run.py 启动
├── requirements.txt
├── .env.example
├── pytest.ini
├── README.md
├── app/
│   ├── __init__.py
│   ├── config.py          # 环境变量 / .env
│   ├── db.py              # 连接、建表、事务、时间工具
│   ├── auth.py            # 密码哈希、JWT
│   ├── deps.py            # get_db / get_settings / get_current_user
│   ├── schemas.py         # Pydantic 请求模型
│   ├── seed.py            # 14 个系统分类
│   ├── main.py            # create_app / 异常处理 / 路由注册
│   └── routers/
│       ├── auth.py
│       ├── accounts.py
│       ├── categories.py
│       ├── transactions.py
│       ├── budgets.py
│       └── stats.py
└── tests/
    ├── conftest.py
    ├── helpers.py
    ├── test_auth.py
    ├── test_accounts.py
    ├── test_categories.py
    ├── test_transactions.py
    └── test_budgets_stats.py
```

## 快速开始

```powershell
cd dango-backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

```bash
# macOS / Linux
cd dango-backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

启动后：

- Swagger：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>
- SQLite：`dango-backend/data/dango.db`（首次启动自动建目录、建表、写系统分类）

也可以直接：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 配置

复制 `.env.example` 为 `.env`，按需修改；程序启动时自动读取，真实环境变量优先。

| 变量 | 默认 | 说明 |
|---|---|---|
| `DANGO_HOST` | `0.0.0.0` | 监听地址；真机调试需要 `0.0.0.0` |
| `DANGO_PORT` | `8000` | 端口 |
| `DANGO_DATABASE` | `./data/dango.db` | SQLite 路径；相对路径相对于 `dango-backend/` |
| `DANGO_JWT_SECRET` | 开发默认串 | **上线必须换成 32 位以上随机串** |
| `DANGO_TOKEN_EXPIRE_MINUTES` | `10080` | token 有效期（分钟），默认 7 天 |
| `DANGO_DEV_TOKEN` | `1` | `1` 启用 `/api/auth/dev-token`；`0` 时该接口返回 404 |
| `DANGO_CORS_ORIGINS` | `*` | 逗号分隔；生产环境收窄为具体域名 |
| `DANGO_RELOAD` | `0` | 开发热重载 |

兼容旧变量名：`DANGO_DB`、`DANGO_JWT_HOURS`、`DANGO_SECRET_KEY`、`DANGO_CORS`。

## 接口

除 `GET /api/health` 和 `/api/auth/register|login|dev-token` 外，全部需要：

```
Authorization: Bearer <token>
```

### 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/register` | 注册，返回 token + user |
| POST | `/api/auth/login` | 登录，返回 token + user |
| GET | `/api/auth/me` | 当前用户 |
| POST | `/api/auth/dev-token` | 调试 token；`DANGO_DEV_TOKEN=0` 时 404 |

```json
{
  "token": "<jwt>",
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 604800,
  "user": {"id": "...", "username": "alice", "created_at": "..."}
}
```

登录失败、缺少 token、token 过期/伪造统一返回 401，并带 `WWW-Authenticate: Bearer`。

### 账户

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/accounts` | `{items, total_balance}`，只含未删除 |
| POST | `/api/accounts` | `name` / `type` / `initial_balance`；新账户 `balance = initial_balance` |
| PUT | `/api/accounts/{id}` | `name` / `initial_balance` / `sort`；改初始余额会同步调整当前余额 |
| DELETE | `/api/accounts/{id}` | 有未删除流水时 409；否则墓碑删除 |
| POST | `/api/accounts/recalc` | 按流水重算全部账户余额，返回 `{items, total_balance}` |

`total_balance` 只汇总未删除账户。账户删除冲突会同时检查 `account_id` 和 `to_account_id`（转账转入账户也算）。

### 分类

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/categories` | 返回数组：系统分类 + 当前用户分类，按 `kind, sort` 升序 |
| POST | `/api/categories` | `name` / `kind`（expense/income）/ `icon` / `color` |
| DELETE | `/api/categories/{id}` | 系统分类 403；自定义分类墓碑删除 |

系统分类 `user_id='__system__'`，所有用户可见、不可删。系统分类 id 用 UUIDv5 生成，重启后保持稳定。

### 流水

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/transactions?month=YYYY-MM&keyword=&page=1&page_size=20` | 分页 + 月份 + 关键字 |
| POST | `/api/transactions` | 新增；转账自动配对并更新两个账户 |
| PUT | `/api/transactions/{id}` | 改金额/分类/日期/备注；先回滚旧 delta 再应用新 delta |
| DELETE | `/api/transactions/{id}` | 墓碑删除 + 反向冲销；转账配对一起删 |

列表返回：

```json
{"items": [], "total": 0, "page": 1, "page_size": 20}
```

- 按 `occurred_at` 倒序；`keyword` 同时匹配 `note` 和分类名；
- 列表不返回 `transfer_in` 配对行；
- `month` 使用左闭右开区间，兼容 `2024-05-06` 和 `2024-05-06T12:30:00` 两种写法；
- `page_size` 最大 100。

新增参数：

```json
{
  "type": "expense|income|transfer",
  "amount": 3000,
  "account_id": "<uuid>",
  "to_account_id": null,
  "category_id": "<uuid>",
  "occurred_at": "2024-05-06T12:30:00",
  "note": "午饭"
}
```

金额必须为正整数（分）。转账时 `to_account_id` 必填且不能与转出账户相同；非转账不接受 `to_account_id`。分类类型必须与流水类型一致。

### 预算

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/budgets?month=YYYY-MM` | 返回 `{month, amount}`；未设置时为 0 |
| PUT | `/api/budgets` | body `{month, amount}`，按 `(user_id, month)` upsert |

### 统计

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/stats/overview?month=YYYY-MM` | 月度汇总 + 支出分类占比 + 每日收支 |
| GET | `/api/stats/monthly-trend?months=6` | 近 N 月收支，1–36 |

`overview` 返回：

```json
{
  "month": "2024-05",
  "income": 50000,
  "expense": 50000,
  "balance": 0,
  "transaction_count": 3,
  "categories": [
    {"category_id": "...", "name": "购物", "icon": "🛍️", "color": "#AB47BC",
     "amount": 30000, "percent": 60.0, "count": 1}
  ],
  "daily": [
    {"date": "2024-05-06", "income": 0, "expense": 30000, "balance": -30000}
  ]
}
```

`monthly-trend` 返回：

```json
{
  "months": 6,
  "start_month": "2024-12",
  "end_month": "2025-05",
  "items": [
    {"month": "2024-12", "income": 0, "expense": 0, "balance": 0}
  ]
}
```

## 关键规则

### 余额

账户余额是缓存，主路径在写流水的事务里实时增减，另提供重算接口兜底：

```
balance = initial_balance
        - Σ(expense.amount where account_id = X)
        + Σ(income.amount where account_id = X)
        - Σ(transfer.amount where account_id = X)       # 转出
        + Σ(transfer.amount where to_account_id = X)    # 转入
```

`transfer_in` 是配对记录，delta 为 0，重算时跳过，避免重复加减。

### 转账配对

一次转账在同一事务内写两条记录：

| 记录 | type | account_id | to_account_id | 余额影响 |
|---|---|---|---|---|
| 转出 | `transfer` | 转出账户 | 转入账户 | 转出账户 `-amount` |
| 转入配对 | `transfer_in` | 转入账户 | 转出账户 | 0（由转出记录统一处理） |

编辑/删除转账时，按「`account_id`/`to_account_id` 互换 + `type='transfer_in'` + `deleted_at IS NULL`」找到配对，两条记录一起更新或一起写墓碑，两个账户余额同步回滚。

### 删除与统计口径

- 所有删除只写 `deleted_at` 和 `updated_at`，表内保留历史行；
- 统计只计算 `type in ('income','expense')` 且 `deleted_at is null`；
- 转账不计收入/支出，也不计入 `transaction_count`；
- 分类占比按“支出”计算，`percent = 分类支出 / 当月总支出 * 100`，保留两位小数；
- 每月趋势以当前月为 `end_month`，向前补零。

### 错误

业务错误统一：

```json
{"detail": "错误说明"}
```

参数校验错误会返回 422，`detail` 为字符串，并附带 `errors` 明细。常见状态码：

- 401：未登录、token 无效/过期、登录失败（带 `WWW-Authenticate: Bearer`）
- 403：删除系统分类
- 404：资源不存在或不属于当前用户
- 409：用户名重复、账户仍有流水、转账配对缺失
- 422：请求参数不合法

### SQLite

每个连接都会设置：

```sql
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```

建库时再设 `PRAGMA journal_mode = WAL`。所有写入使用 `BEGIN IMMEDIATE`，失败整体回滚。SQL 全部参数化。

## 测试

```powershell
cd dango-backend
.\.venv\Scripts\python.exe -m pytest tests -v
```

最近一次实际运行结果：

```
83 passed in 19.41s
```

覆盖范围：

- 注册、登录、重复注册、错误密码、无 token、伪造 token、dev-token 开关；
- 账户 CRUD、初始余额调整、排序、删除冲突、墓碑、余额重算；
- 分类系统/自定义、排序、系统分类只读、跨用户隔离、重复分类；
- 流水分页、月份、关键字（备注/分类名/LIKE 通配符转义）、转账配对、编辑、删除、反向冲销；
- 预算默认值、读写、upsert、隔离；
- 统计收入/支出/结余/笔数、分类占比、每日趋势、月度趋势、转账排除、删除排除、用户隔离；
- 空字符串可选 id 归一化为 NULL。

测试全部使用 `tmp_path` 下的临时 SQLite，不读写正式库。

说明：测试依赖按方案固定 `httpx==0.27.*`；FastAPI/Starlette 1.x 对 `starlette.testclient` + httpx 0.27 有上游弃用提示，`pytest.ini` 仅屏蔽该提示，不影响测试结果。

## 部署提醒

1. `DANGO_JWT_SECRET` 换成 32 位以上随机串；
2. `DANGO_DEV_TOKEN=0` 关闭调试 token；
3. `DANGO_CORS_ORIGINS` 收窄为前端域名；
4. 前面套 HTTPS / 反向代理；
5. 定期备份 `data/dango.db`；
6. 生产多进程写 SQLite 前，评估改用 PostgreSQL。

## 不做的事

- 不实现 `/api/sync/push`、`/api/sync/pull`、`/api/sync/reset`；
- 不做客户端本地库、离线队列、LWW 冲突合并；
- 不做多人共享账本、账单导入、OCR、周期账单。
