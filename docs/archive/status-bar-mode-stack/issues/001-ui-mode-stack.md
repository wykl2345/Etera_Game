# Issue 1: UI 模式栈 — 状态栏可见性统一管理

## Parent

[PRD: 状态栏显示时机修复 & UI 模式栈](../PRD.md)

## What to build

`WindowManager` 维护一个 UI 模式栈，声明每种模式下状态栏的可见性。引擎层进出子界面时调用 `push_mode()` / `pop_mode()`，状态栏自动响应，不再手动操作 widget。

模式与可见性规则：

| 模式 | 状态栏 |
|------|--------|
| `main_menu` | 隐藏 |
| `game` | **显示** |
| `settings` | 隐藏 |
| `save` | 隐藏 |
| `load` | 隐藏 |
| `character_detail` | 隐藏 |

栈操作 API：`push_mode`（入栈）、`pop_mode`（出栈，栈底保护）、`reset_mode`（清空栈）、`current_mode`（查询）。

当前消费者：设置面板已接入 `push_mode("settings")` / `pop_mode()`。`save` / `load` / `character_detail` 模式规则已预声明，后续接入时只需调 API。

旧方法 `show_status_bar()` / `hide_status_bar()` 保留为委托方法，向后兼容。

## Acceptance criteria

- [ ] 开始新游戏 → 栈 `["main_menu", "game"]`，状态栏可见
- [ ] 继续游戏 → 同上
- [ ] 游戏内打开设置 (主菜单 [3]) → 栈推入 `"settings"`，状态栏隐藏
- [ ] 关闭设置返回 → 栈弹出，状态栏恢复可见
- [ ] F5 重启引擎 → 栈重置为 `["main_menu"]`，状态栏隐藏，回到主菜单
- [ ] `pop_mode()` 在栈底时拒绝弹出并记录 warning
- [ ] 传入未知模式时回退到 `"main_menu"` 并记录 warning

## Blocked by

- ~~状态栏显示时机修复~~（已完成）

None — 基础设施已实现，待验证。
