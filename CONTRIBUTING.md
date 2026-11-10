# 贡献规范

本文件是 Dango Ledger / 团子账本 的代码规范。提交前请先读一遍。

## 一、分支与提交

- 主分支 `main` 保持可运行；开发用 `feat/xxx`、`fix/xxx`、`docs/xxx`、`chore/xxx`。
- 提交信息使用 **Conventional Commits**：

```
feat(backend): 新增预算接口
fix(frontend): 修复明细页月份筛选
docs: 补充接口说明
refactor(backend): 抽取余额变更函数
test: 补充转账编辑用例
chore: 升级 ruff
```

- 一个提交只做一件事；不要混入无关格式化。
- 不提交 `.venv/`、`node_modules/`、`unpackage/`、`data/`、`*.db`。

## 二、Python / 后端

- Python 3.10+；类型注解必须写；数据库用标准库 `sqlite3`，不引入 ORM。
- 格式与静态检查统一用 **Ruff**（配置在 `dango-backend/pyproject.toml`）：

```bash
cd dango-backend
.venv\Scripts\python.exe -m ruff format .
.venv\Scripts\python.exe -m ruff check --fix .
.venv\Scripts\python.exe -m pytest tests -q
```

- 行宽 100；引号双引号；LF；4 空格缩进。
- FastAPI 的 `Depends(...)` 默认参数是官方写法，Ruff 的 `B008` 已在配置里按文件忽略，不要改写成 `Annotated` 以外的奇怪形式（如需统一可后续整体迁移）。
- 业务规则：
  - 金额一律整数「分」，禁止浮点入库；
  - 主键 UUID；删除写 `deleted_at` 墓碑；
  - 所有业务查询必须带 `user_id`，系统分类 `__system__` 只读；
  - 余额变更、转账配对、编辑回滚、删除冲销必须在同一个 SQLite 事务内；
  - 统计只算 `income` / `expense`，转账不计收支。
- 不在业务代码里 `print` 调试；错误交给 FastAPI 的 `HTTPException`，统一 `{detail: "..."}`。
- 新增接口必须补 pytest 用例；测试用 `tmp_path` 临时数据库，不碰开发库。

## 三、前端 / uni-app x

- 项目是 **uni-app x 蒸汽模式**，页面文件 `.uvue`，脚本用 `<script setup lang="uts">`（当前项目基线）；HBuilder V 支持 UTS，如后续整体改 `lang="ts"` 需单独验证。
- 只支持组合式 API，禁止选项式、`mixin`。
- **样式只用简单 class**，层级用 BEM（`.entry__title`）；禁止 `.a .b`、`>`、属性选择器等运行时关系选择器。SCSS 可以用，但产物必须落到简单 class。
- 组件样式默认隔离（样式隔离 2.0）；需要外部控制时用 `defineOptions({ styleIsolation: 'app' })` 并写明原因。
- 数据流固定：

```
页面 .uvue → Pinia store → services/api.uts → 后端
```

  - 页面不直接 `uni.request`；
  - store 不直接拼 SQL / 不读写本地存储；
  - **所有业务数据走接口，禁止 localStorage / Storage 缓存账本数据**；
  - token 只放内存（重启重新登录），不要持久化。
- HTTP 方法：更新用 **PUT**，不要用 PATCH（微信小程序 `wx.request` 不支持 PATCH）。
- 金额只做展示格式化（`utils/money.uts`）；余额、统计、转账配对以服务端返回为准，前端不重复计算。
- 命名：文件小写下划线或短横线；变量 camelCase；常量 UPPER_SNAKE；品牌文案「团子账本 / Dango Ledger」。
- 不引入 wot-design-uni、z-paging、uCharts；需要 UI 组件时用内置组件或 uni-ui x（`uni_modules`）。
- API 边界允许 `any`，业务函数尽量写具体类型/结构说明。

## 四、接口约定

- 路径统一 `/api/...`；JSON 字段 snake_case。
- 认证：`Authorization: Bearer <token>`；401 统一清 token 并回登录页。
- 列表返回 `{items, total, page, page_size}`；账户列表额外带 `total_balance`；分类列表直接返回数组。
- 错误统一 `{detail: "..."}`；可预期的业务失败用 4xx，不要用 200 包错误。
- 金额字段一律整数分；时间用 ISO8601 字符串，月份 `YYYY-MM`。

## 五、目录约定

```
dango-backend/
  app/            业务代码（routers / db / auth / schemas）
  tests/          pytest
  pyproject.toml  Ruff 配置

dango-frontend/
  pages/          页面（.uvue，一个页面一个目录）
  stores/         Pinia
  services/       api.uts
  utils/          money / date
  static/         静态资源
  manifest.json   uni-app x + 蒸汽模式
  pages.json      路由
```

## 六、提交前检查

```powershell
# 后端格式 + lint + 测试
.\scripts\check.cmd

# 前端静态检查（manifest / pages.json / 页面文件）
.\scripts\check.cmd -Frontend
```

前端编译/运行在 **HBuilder V** 中完成：打开 `dango-frontend/`，运行到 H5 / 微信小程序 / Android，确认无编译错误。HBuilder V 没有 CLI，`-Frontend` 只做静态检查，不能替代 GUI 编译。

如果 PowerShell 允许执行脚本，也可以直接运行 `.\scripts\check.ps1`；否则用 `.cmd` 包装（会自动加 `-ExecutionPolicy Bypass`）。

也可安装 pre-commit（在仓库根目录执行）：

```powershell
dango-backend\.venv\Scripts\python.exe -m pip install -r dango-backend\requirements-dev.txt
dango-backend\.venv\Scripts\pre-commit.exe install
dango-backend\.venv\Scripts\pre-commit.exe run --all-files
```

（`pre-commit` 首次运行需要访问 GitHub 拉取 hook 仓库。）

## 七、PR 检查清单

- [ ] 后端 `ruff format --check`、`ruff check`、`pytest` 全部通过
- [ ] 前端 HBuilder V 编译/运行 H5 通过
- [ ] 新增/修改接口有测试或手测记录
- [ ] 金额、余额、转账相关改动逐条验证
- [ ] 没有提交密钥、`.env`、数据库文件、构建产物
- [ ] 提交信息符合 Conventional Commits
