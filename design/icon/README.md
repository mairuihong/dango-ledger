# 三彩团子 · 图标设计

为「团子账本 / Dango Ledger」设计的应用图标，灵感来自日式花见团子（三色团子）与游戏《原神》中的料理「三彩团子」的意象：**粉、白、绿三颗团子串在竹签上**。

> 说明：这是原创绘制，没有使用《原神》或任何第三方的图片素材；只借鉴了「三色团子串」这一通用造型。

## 设计说明

- **造型**：三颗饱满的团子向左倾斜约 **45°** 串在竹签上，顶部露出签尖，底部露出签尾；背景是自上而下的暖色和纸渐变，配两朵樱花与柔和的圆形光晕。
- **配色**：粉（樱花）、乳白（原味）、抹茶绿（草饼），对应三彩团子的经典三色；竹签用暖木色，避免和团子抢视觉。
- **风格**：扁平 + 柔和径向渐变，强调圆润、可信赖、轻量，适合记账类应用；缩到 48px 仍能看出「三颗团子 + 竹签」。
- **安全区**：主体在 1024 画布中央约 70% 区域内，利于 iOS/Android 的圆角/圆形裁切。

## 配色

| 用途 | 色值 |
|---|---|
| 背景起始 | `#FFFBF5` |
| 背景结束 | `#FFD9BE` |
| 樱花粉团子 | `#FAB6C5` → `#DE7B93` |
| 乳白团子 | `#FFFFFF` → `#E3C9A5` |
| 抹茶团子 | `#BCE0B2` → `#7DB473` |
| 竹签 | `#E9BC80` / `#C08848` |
| 樱花点缀 | `#F3A9BA` |

## 文件

```
design/icon/
├── dango-tricolor.svg              矢量源文件（1024 画布）
├── dango-tricolor-1024.png         主图 / App Store
├── dango-tricolor-512.png
├── dango-tricolor-192.png          Android xxxhdpi
├── dango-tricolor-144.png          Android xxhdpi
├── dango-tricolor-96.png           Android xhdpi
├── dango-tricolor-72.png           Android hdpi
├── dango-tricolor-48.png           小图标 / favicon
└── dango-tricolor-rounded-1024.png 圆角预览（透明四角）
```

前端已同步到 `dango-frontend/static/icon/`，并在 `manifest.json` 里配置了 Android / iOS 图标。

## 重新导出

需要 `@resvg/resvg-js`（Node）：

```bash
npm i @resvg/resvg-js
node -e "const{Resvg}=require('@resvg/resvg-js');const fs=require('fs');const svg=fs.readFileSync('dango-tricolor.svg');for(const s of [1024,512,192,144,96,72,48]){const r=new Resvg(svg,{fitTo:{mode:'width',value:s}});fs.writeFileSync('dango-tricolor-'+s+'.png',r.render().asPng())}"
```

圆角版本用 Pillow 对 1024 PNG 加 224px 圆角遮罩即可。

## 使用建议

- App Store / Google Play：用 `-1024.png` 全出血版本，不要在图标内再画圆角。
- Android 自适应图标：可把主体放在安全区（中心 66%），背景单独一层；当前版本可直接用。
- 深色模式/单色图标：后续可基于 SVG 去掉背景与樱花，只保留三颗团子和竹签。
