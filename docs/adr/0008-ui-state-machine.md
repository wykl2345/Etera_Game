# ADR-0008: UI 根界面 + 覆盖层状态机，禁止隐式回退

> 2026-11-03 更新：小游戏已迁到 Overlay Host，模式栈删除；本文保留当时的决策记录，
> 当前实现见 `docs/adr/0009-overlay-host.md`。

`docs/planning/` 记录了一个现象：页面切换时偶发进入只有背景/主题色、没有文字和按钮的默认空壳。
排查确认当前代码存在多条可进入空壳的路径：

- `popMode()` 在模式栈为空时回退到 `game`（重复 finish / 额外 pop 即触发）；
- 小游戏 `finishMinigame` 不幂等，重复调用会二次出栈；
- 睡觉、读档、`event.done`、`minigame.start` 是异步消息，玩家已回主菜单/Hub 后到达仍会改界面；
- Hub 行动被后端拒绝时，前端已切到 `game` 并清空内容，却没有回收；
- 读档成功后 `panel='load'` 未关闭，面板继续盖在新界面上。

## 决策

把 UI 状态明确拆成三层，并让非法状态不可表达：

1. **根界面**只有 `main_menu` / `hub` / `game` 三种，页面级切换走 `resetMode()`，清空模式栈。
2. **覆盖层**当前只有 `minigame`；`pushMode()` 只接受覆盖层，重复压入是 no-op。
3. **系统面板**（存档/读档/设置/角色/商店/背包/送礼）只存于 `panel`，不再进入 `uiMode`。
4. **空栈 pop 是 no-op**，绝不回退到任何隐式默认模式。
5. 小游戏结束幂等：`activeMinigame` 为空时直接返回；取消走 `cancelMinigame()`。
6. 异步消息做哨兵：读档用 `pendingLoadEpoch`/`uiEpoch` 校验；剧本结束用 `pendingEvent`
   （事件名 + 代际）匹配；睡觉只在 `hub` 处理；`minigame.start` 只在 `game` 且无活动小游戏时处理。
7. 所有 `uiMode`/`modeStack` 写入走 `transitionTo()`，保留最近 200 条状态转移
   （`window.__eteraUiLog`；`localStorage.etera.uiDebug=1` 打开控制台输出）。
8. 未知模式渲染可见恢复页，而不是空白 `GameScreen`。

纯状态迁移放在 `frontend/src/stores/uiMode.ts`（无 Vue/Pinia 依赖），store 只负责调用与记录日志；
回归用例在 `frontend/src/stores/game.test.ts`。

## Consequences

- 空壳的三类已知触发路径（空栈回退、迟到消息、失败行动）都有回归测试覆盖；
- `UiMode` 去掉了从未使用的 `settings/save/load/character_detail`，系统面板统一走 `panel`；
- 日志是环形缓冲，不改变协议、存档或 DSL；前端新增 Vitest（`npm test`），后端测试不受影响；
- 这不是完整的 Overlay Host 抽象：`panel` 仍是硬编码枚举。后续接入第三方 UI 模块时，
  可沿用“根界面 + 覆盖层 + 实例 ID/结果回传”的同一套边界，再抽独立模块契约。
