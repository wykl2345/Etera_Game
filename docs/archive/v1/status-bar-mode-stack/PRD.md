# PRD: 状态栏显示时机修复 & UI 模式栈

## Problem Statement

玩家在开始新游戏后，顶部状态栏（天数、时段、天气、金钱、HP/MP 条）在序章文本和选项出现时完全不可见，直到点击选项之后才突然出现。状态栏应该在进入游戏非标题界面的第一时间就显示，而不是延迟到脚本执行完第一段交互之后。

更深层的问题：状态栏的显示/隐藏由引擎各处分散调用 `show_status_bar()` / `hide_status_bar()` 控制，缺乏统一的 UI 层级管理机制。设置面板、存档界面、角色详情等子界面打开时，状态栏应自动隐藏，但当前没有这个能力。

## Solution

**两处改动：**

1. **修复显示时机**：将"舞台搭建"（加载角色 + 显示状态栏）从 `on_game_start` 事件处理器中提升到事件发射之前。引擎层先完成 UI 框架搭建，再通知脚本开始表演，确保脚本运行时状态栏已在顶部可见。

2. **UI 模式栈**：`WindowManager` 维护一个模式栈，声明每种 UI 模式下状态栏的可见性。引擎层通过 `push_mode()` / `pop_mode()` 进出子界面，状态栏自动响应，不再需要手动调用 show/hide。

## User Stories

1. As a player, I want to see the status bar (day, time, weather, money, HP, MP) as soon as I start a new game, so that I know my character's state from the very first line of story text.
2. As a player, I want the status bar to remain visible throughout gameplay, so that I can monitor my stats at any time without needing to trigger an update.
3. As a player, I want the status bar to hide when I open the settings panel, so that the settings menu has a clean full-screen appearance.
4. As a player, I want the status bar to hide when I open the save/load interface, so that the save slots use the full screen space.
5. As a player, I want the status bar to hide when I view a character detail popup, so that the popup isn't competing with the game HUD for attention.
6. As a player, I want the status bar to reappear when I close any sub-interface and return to gameplay, so that the HUD is restored without me noticing.
7. As a mod author, I want to set player stats via Lua API (`data.set_stat`) and see the status bar update immediately, so that stat changes are reflected in the UI without extra code.
8. As a developer, I want to add a new UI mode (e.g., a crafting screen) by declaring one visibility rule, so that I don't need to remember to manually hide/show the status bar in every entry/exit path.

## Implementation Decisions

### 舞台搭建前置

引擎启动新游戏的执行顺序从：

```
emit("on_game_start")
  → load characters
  → show status bar
  → run intro script
```

改为：

```
load characters
show status bar
emit("on_game_start")
  → run intro script (status bar already visible)
```

`_on_game_start` 事件处理器简化为纯日志记录，不再承担初始化职责。

### UI 模式栈

`WindowManager` 新增模式栈，声明式规则：

| 模式 | 状态栏可见 |
|------|-----------|
| `main_menu` | 隐藏 |
| `game` | **显示** |
| `settings` | 隐藏 |
| `save` | 隐藏 |
| `load` | 隐藏 |
| `character_detail` | 隐藏 |

栈操作：
- `push_mode(mode)` — 入栈，自动应用当前模式的可见性规则
- `pop_mode()` — 出栈，恢复上级模式状态（栈底不可弹出）
- `reset_mode(mode)` — 清空栈并设为单一模式（用于重启/返回标题）
- `current_mode()` — 查询栈顶模式

引擎层调用点：
- 开始新游戏 / 继续游戏 → `push_mode("game")`（或通过 `show_status_bar()` 委托）
- 重启引擎 F5 → `reset_mode("main_menu")`（或通过 `hide_status_bar()` 委托）
- 进入设置面板 → `push_mode("settings")` ... `pop_mode()` (finally)
- 后续存档/读档/角色详情 → 同上模式

旧方法 `show_status_bar()` / `hide_status_bar()` 保留为委托方法，确保向后兼容。

### 状态栏刷新

`GameStatusBar` 通过事件总线订阅 `on_game_start`、`on_day_begin`、`character_stat_changed` 等事件，数据变更时自动从 `GameContext` 拉取全量刷新。模式栈只控制可见性，不控制数据刷新。

## Testing Decisions

### 测试接缝

最高可测接缝为 `WindowManager` 的模式栈 API：

| 操作 | 预期 |
|------|------|
| 初始化后 | `current_mode()` = `"main_menu"`，状态栏隐藏 |
| `push_mode("game")` | 状态栏 widget visible，`current_mode()` = `"game"` |
| `push_mode("settings")` | 状态栏 widget hidden，`current_mode()` = `"settings"` |
| `pop_mode()` | 回到 `"game"`，状态栏重新 visible |
| `pop_mode()` again | 拒绝（栈底保护），返回 None |
| `reset_mode("main_menu")` | 栈 = `["main_menu"]`，状态栏 hidden |
| 未知模式 `push_mode("unknown")` | 回退到 `"main_menu"` |

### 测试原则

- 只测试外部行为（模式 → 状态栏可见性），不测试内部 widget 状态
- 不需要启动 Lua 沙箱或事件总线即可覆盖全部规则
- 参考现有代码中 `GameStatusBar` 的 `setFixedHeight(52)` 和 `hide()/show()` 行为作为断言依据

## Out of Scope

- 底部功能栏（分割线 + 保存/读取/设置按钮）— Phase 2
- 存档界面的多槽位翻页 UI — Phase 2
- 角色详情弹窗的具体内容渲染 — Phase 3
- 设置面板的具体控件（音量滑块、字体大小等）— Phase 4
- 状态栏本身的扩展（天气图标、Buff/Debuff 标记）
- 模式栈对其他 UI 元素（如图像区、底部功能栏）的联动控制

## Further Notes

- 当前模式栈仅控制状态栏可见性。后续底部功能栏、图像区等全局 UI 元素如需统一管理，可在 `_apply_mode()` 中扩展。
- `GameStatusBar` 订阅了 `on_game_start` 事件做刷新，但由于 `show_status_bar()` 已显式调用 `refresh()`，该订阅在当前流程中是冗余但无害的。
- 如果未来 Lua 脚本需要临时隐藏状态栏（如全屏 CG 事件），可通过新增 Lua API 调用 `push_mode("cg")` / `pop_mode()` 实现，无需修改引擎代码。
