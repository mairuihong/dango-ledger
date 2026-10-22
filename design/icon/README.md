# 三彩团子 · 图标设计

为「团子账本 / Dango Ledger」设计的应用图标，灵感来自日式三色团子与 iconfont 图标「三色团子」：**黄、粉、绿三颗团子串在深棕竹签上**。

> 说明：这是原创绘制，没有使用《原神》、iconfont 或任何第三方的图片素材；只借鉴了「三色团子串」的通用造型与配色。

## 设计说明

- **造型**：黄、粉、绿三颗团子呈 **45°** 斜串，竹签只从右下方露出，上方不露签尖；粉团子夹在中间，被黄、绿两颗压住，形成 iconfont 那种层叠关系。
- **配色**：芥末黄、莓粉、抹茶绿，配深棕细竹签；平涂 + 白色高光，接近 iconfont 的扁平风格。
- **背景**：白色 → 浅米色的纯色上下渐变，另加蓝环、绿点、粉环三颗小装饰，和参考图标一致。
- **风格**：扁平、清爽、圆润；缩到 48px 仍能看出「三颗团子 + 深色竹签」。
- **安全区**：主体在 1024 画布中央约 70% 区域内，利于 iOS/Android 的圆角/圆形裁切。

## 配色

| 用途 | 色值 |
|---|---|
| 背景起始 | `#FFFFFF` |
| 背景结束 | `#FFF0E4` |
| 黄色团子 | `#E3CB50` |
| 粉色团子 | `#D086AB` |
| 绿色团子 | `#C1D28D` |
| 竹签 | `#6B4226` → `#2F190D` |
| 蓝色圆环 | `#7AAEE3` |
| 绿色圆点 | `#8FBF6A` |
| 粉色圆环 | `#E7A8C4` |

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
