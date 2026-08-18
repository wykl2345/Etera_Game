# ADR-0005: 小游戏独立 Canvas 层

未来内嵌小游戏（杀戮尖塔式肉鸽）以独立 Canvas 组件挂载到 `frontend/src/games/`，自有 requestAnimationFrame 渲染循环，与 Vue 主框架解耦；Vue 只做外壳与状态桥接（进出模式、结果回写 GameContext）。原因是文本冒险主 UI 极轻量，而肉鸽战斗是渲染密集的，混入 Vue 组件树会互相干扰；独立渲染层保证 60fps 且不拖累主界面。

**Consequences**: 小游戏逻辑全部 Canvas 2D 实现；与后端通过既有 WS 通道或独立 minigame API 通信（Phase 4 评估）。
