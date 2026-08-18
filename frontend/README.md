# Etera_Game 前端 — Vue 3 + Vite + TypeScript

叙事界面（gal 布局平移）+ 系统界面（Web 现代化，ADR-0006）。

## 开发

```bash
npm install        # 首次
npm run dev        # http://127.0.0.1:5173（需后端已启动，见 backend/README.md）
npm run type-check # vue-tsc 类型检查
npm run build      # 构建到 dist/
```

## 运行前提

1. 后端已启动：`cd ../backend && ../.venv/bin/python main.py`（WS :8765，静态资源 :8766）
2. 浏览器打开 http://127.0.0.1:5173

## 联调验收

```bash
node e2e-check.mjs   # 模拟浏览器走完整流程（序章 → 日常事件循环）
```

## 结构

```
src/
├── ws/client.ts      # WS 客户端（协议见 docs/architecture.md §四）
├── stores/game.ts    # Pinia：uiMode / 文本流 / 选项 / 立绘背景 / 输入
└── components/
    ├── MainMenu.vue      # 主菜单（现代化 Web 风格）
    ├── GameScreen.vue    # 游戏画面容器
    ├── TextFlow.vue      # 终端风格文本流
    ├── ChoiceMenu.vue    # 选项按钮（嵌入文本流）
    ├── BackgroundLayer.vue / CharacterLayer.vue
    └── InputOverlay.vue  # 文字输入（ui.ask_input）
```
