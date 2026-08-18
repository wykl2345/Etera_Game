# ADR-0001: 前后端分离 + 浏览器渲染

v1 为 Python + PySide6 桌面应用，引擎核心完成度高但 Qt 渲染/布局层是最大负担（状态栏时机、模式栈、选项嵌入等）。我们决定前后端分离：浏览器（Vue 3）负责一切渲染与排版，Python 后端（asyncio）专注游戏逻辑，经 WebSocket (JSON) 通信。原因是 Web 技术栈在排版/动画/主题上成本远低于 Qt，且天然跨平台。

**Consequences**: 调度器必须从 Qt 嵌套 QEventLoop 改为 asyncio 协程；37 个 Lua 指令的阻塞语义需经 WS 的 requestId 机制重新实现；渲染相关能力（立绘淡入淡出等）从 Qt 组件迁移到 CSS/JS。
