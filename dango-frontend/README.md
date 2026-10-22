# 团子账本 · Dango Ledger 前端

uni-app x **蒸汽模式**（HBuilderX 项目根目录）。Vue3 组合式 API + Pinia，所有业务数据走 HTTP 接口，前端不落盘。

## 环境

- HBuilderX 5.26+（本机安装在 `C:\software\code\HBuilderX`；蒸汽模式见 manifest 的 `"uni-app-x": { "vapor": true }`）
- Node.js / npm（安装 Pinia）

## 安装与运行

```bash
cd dango-frontend
npm install
```

用 HBuilderX 打开本目录，然后运行到 Web / 微信开发者工具 / Android 真机。

> HBuilderX 5.26 的 Web 平台仍以 VDOM 模式运行（官方设计），App 端才是蒸汽模式。

命令行编译 Web（需要 HBuilderX 已启动）：

```bash
"C:\software\code\HBuilderX\cli.exe" publish web --project "D:\testProject\团子账本\dango-ledger\dango-frontend" --webTitle "团子账本"
```

产物在 `unpackage/dist/build/web`。

## 接口地址

改 `config.uts`：

```ts
export const API_BASE = 'http://127.0.0.1:8000'
```

- H5 本机：`127.0.0.1`
- 真机 / 小程序：改成电脑局域网 IP，例如 `http://192.168.1.100:8000`
- 后端启动：`cd dango-backend && .venv\Scripts\python run.py`

## 目录

```
pages/            7 个页面（.uvue）
stores/           Pinia：auth / ledger / stats / budget
services/api.uts  uni.request 封装 + 全部接口
utils/            money（元⇄分）、date
config.uts        API_BASE
main.uts          Vue + Pinia
App.uvue          全局样式
manifest.json     应用信息 + 蒸汽模式
pages.json        路由 / tabBar
```

## 图标

应用图标为原创的「三色团子」：粉 / 乳白 / 抹茶绿三颗团子以 45° 串在深棕竹签上，白色 → 浅米色上下渐变背景，点缀蓝环、绿点、粉环。

- 源文件与多尺寸 PNG：仓库根目录 [design/icon](../design/icon/README.md)
- 前端使用：`static/icon/`（Android 72/96/144/192、iOS 1024、favicon 48）
- 已在 `manifest.json` 配置 Android / iOS 图标，`index.html` 配置 favicon

## 约定

- 所有数据来自接口；Pinia 只存当前会话内存，刷新/重启重新拉取。
- token 只放内存，重启需重新登录（按「不用本地储存」约束）。
- 金额展示用「分」整数格式化；余额和统计以服务端返回为准。
- 样式只用简单 class（蒸汽模式 CSS 子集），不要写复杂后代选择器。

完整规范见 [CONTRIBUTING.md](../CONTRIBUTING.md)；提交前运行 `..\scripts\check.ps1 -Frontend`（需要 HBuilderX 已启动）。
