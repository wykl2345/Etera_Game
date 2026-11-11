# ADR-0009: Overlay Host（P3）——小游戏迁移为覆盖层模块

P3 的目标是验证“常驻主界面 + 独立 UI 模块/浮窗宿主”的架构，而不是继续用 `uiMode` 切换整页。
迁移前小游戏是唯一还会切 `uiMode` 的临时 UI：打开时主菜单/Hub 被卸载，关闭依赖
`modeStack.pop()`，二次 pop 或迟到消息都可能落回没有内容的 `game` 空壳（ADR-0008 已做兜底，
但根因仍是“覆盖层伪装成根界面”）。

## 决策

1. **根界面只有 3 个**：`main_menu` / `hub` / `game`；`UiMode` 不再包含 `minigame`，模式栈删除。
2. 新增 **Overlay Host**：
   - `store.overlay: { id, moduleId, input, requestId } | null`；
   - 同一时间只允许一个覆盖层；打开时根界面保持挂载、`uiMode` 不变；
   - 模块注册表 `frontend/src/overlays/index.ts`，目前注册 `minigame`。
3. 模块契约：组件接收 `input`，通过 `complete(result)` / `cancel()` 事件交回结果；
   store 负责关闭、回传 `requestId`、实例 id 校验与日志。模块不直接改 `uiMode`。
4. `minigame.start` / `minigame.result` 的 DSL 语义不变；只是前端从模式切换改为覆盖层。
   小游戏打开期间 `canPersist=false`，完成/取消后关闭并恢复自动播放。
5. 覆盖层打开/关闭写入同一份 UI 转移日志（`action: overlay-open/overlay-close`，
   带 `overlay.id/moduleId`），仍可通过 `window.__eteraUiLog` 导出。
6. 系统面板（存档/设置/商店/背包等）继续走 `panel`，不属于本次迁移；P4 可注册
   非小游戏模块并复用同一份输入/结果契约。

## Consequences

- 主菜单/叙事界面在小游戏打开时不再卸载；关闭后原界面原样保留，不需要“返回上一模式”。
- 二次完成、旧实例迟到回调、重复 `minigame.start` 都被实例 id / `overlay` 判空挡住；
  不再存在空栈 pop 回退 `game` 的路径。
- UI 状态机进一步简化为“根界面 + 一个覆盖层 + 系统面板”，为 P4 的第三方模块契约留出边界。
- 当前覆盖层仍是项目内打包的 Vue 组件（同一页面上下文），没有 iframe/沙箱隔离；
  本地信任模型与模块权限留到后续阶段。
- 回归：前端 store 27 项（含 Overlay 生命周期/迟到实例/日志），真实浏览器验证了
  “主菜单打开小游戏→返回仍在主菜单”和“序章 DSL 小游戏→退出后对话继续”。
