# Etera_Game (EE1)

Emuera/ERA 风格叙事文字冒险游戏引擎，前后端分离架构。

- **后端**: Python 3.12 + asyncio（Lua 沙箱 + 事件总线 + 状态 + 存档）
- **前端**: Vue 3 + Vite（浏览器渲染，终端风格 UI）
- **通信**: WebSocket (JSON)，37 个 Lua 指令为 Mod 契约（见 DSL.txt）
- **文档**: docs/architecture.md（架构）、docs/requirements.md（需求）、CONTEXT.md（领域词汇）
- **旧版**: v1 文档与源码见 docs/archive/v1/ 与 git tag pre-web-refactor
