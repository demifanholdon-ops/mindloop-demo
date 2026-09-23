# MindLoop 启念 · UI V2.0

此目录是当前视觉开发版本。粉色背景、黑色头部、深浅两撮毛发、连体蛋形眼睛、粉色嘴唇与腮红、黄色身体。

从工作区根目录（上两级）运行 `npm start`，打开 `/versions/V2.0/index.html#home`。版本档案和切换在工作区根目录维护。

- `src/character.js`：独立 SVG Web Component，角色形状、颜色、弹簧反馈及手势。
- `src/style.css`：手机布局与全局粉色视觉。
- `src/app.js`：四个页面与演示交互，独立存储键 `mindloop-ui-V2.0`。
- `src/data.js`：日期与演示数据。
- `tests/data.test.js`：日期、月历、回归比例验证。
- `reference/`：用户提供的两张造型 / 色彩参考。

执行 `npm run check` 和 `npm test` 可检查本版本。在工作区根目录执行 `npm run verify:v1`，确认旧版本未变。

详细设计记录位于 `../../releases/MindLoop-UI-V2.0-设计记录.md`。不要修改 `../V1.0/`。
