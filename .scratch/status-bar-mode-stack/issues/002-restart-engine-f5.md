# Issue 2: 菜单 "重启引擎 F5" 无效

## Parent

[PRD: 状态栏显示时机修复 & UI 模式栈](../PRD.md)

## What to build

菜单栏「游戏 → 重启引擎 (F5)」在当前多个场景下行为异常，需要真正中止所有脚本并安全返回主菜单。

### 已修复（信号连接）

`WindowManager._create_menu()` 在 `__init__` 中执行时 `_restart_callback` 尚未注入，导致 `triggered.connect()` 被短路跳过。已改为始终连接内部槽 `_on_restart_triggered`，运行时检查回调是否存在。

### 待修复（脚本中止逻辑）

以下三个 bug 根因相同：`scheduler.stop_all()` 只退出嵌套 QEventLoop，但 Lua 脚本仍在 Python 调用栈上继续执行，无法真正做到中止。

#### Bug 1：标题界面按 F5 直接进入游戏

按 F5 → `_restart_engine()` → `stop_all()` 退出主菜单的 `wait_for_choice()` 嵌套循环。`wait_for_choice()` 默认返回 `1`，`_show_main_menu()` 将其解读为"开始新游戏"，引擎继续执行 `_start_new_game()`。

**预期**：主菜单按 F5 应无操作，或重新显示主菜单。

#### Bug 2：游戏中选项出现前按 F5，脚本继续输出

按 F5 → `stop_all()` 退出 intro.lua 的 `ui.ask_choice()` 等待循环。Lua 拿到默认返回值 `1`（对应"去村里转转"），脚本继续执行后续文本，输出：

> 你决定去村里的市集看看。
> 新的旅程开始了……

在此状态下再次按 F5 会触发 Bug 3。

**预期**：任意时刻按 F5，脚本立即停止，不输出任何后续内容。

#### Bug 3：游戏中选择完成后按 F5，直接关闭窗口

intro.lua 执行完毕后主事件循环 `_qt_app.exec()` 正在运行。按 F5 → `_restart_engine()` → `_qt_app.quit()` 退出主循环。`run()` 中 `exec()` 返回后执行 `if not self.window.isVisible()`，此时窗口可能尚未恢复可见状态，条件为 True，直接 `break` 退出程序。

**预期**：任意时刻按 F5，引擎安全返回主菜单，窗口不关闭。

### 根因

`ScriptScheduler.stop_all()` 当前实现：

```python
def stop_all(self) -> None:
    if self._active_loop and self._active_loop.isRunning():
        self._active_loop.exit(1)
    self._current_script = None
    self._state = ScriptState.IDLE
```

仅退出嵌套 QEventLoop，不中断 Lua 调用栈。`wait_for_choice()` 返回默认值后，`run_script_sync()` 中的 `lua.execute(code)` 继续执行剩余 Lua 代码。

### 修复方向

1. 调度器增加 `_aborted` 标志，`stop_all()` 设置该标志
2. `wait_for_choice()` / `wait_for_input()` 检测到 `_aborted` 后抛出专用异常，穿透 Lua 调用栈
3. `run_script_sync()` 捕获该异常，调用 `lua.abort()`（或等效机制）真正终止 Lua 执行
4. `_restart_engine()` 不再通过 `_qt_app.quit()` 退出，改用模式栈 `reset_mode("main_menu")` + 清空控制台 → `_show_main_menu()` 自然接管
5. 主菜单的 `wait_for_choice()` 调用点需特殊处理：`stop_all()` 不应影响主菜单循环，或使用独立标志通知主循环重新显示菜单

## Acceptance criteria

- [ ] **Bug 1**: 主菜单按 F5，引擎留在主菜单（不进入游戏）
- [ ] **Bug 2**: 游戏中选项等待时按 F5，脚本立即停止，不输出任何后续文本
- [ ] **Bug 3**: 游戏中选择完成后按 F5，引擎安全返回主菜单，窗口不关闭
- [ ] 脚本中止后 `script.error` 或 `script.aborted` 事件被发射，便于日志和调试
- [ ] 重启回调未设置时（理论上不应发生），F5 记录 warning 而非崩溃

## Blocked by

- [x] Issue 1: 状态栏显示时机修复 + UI 模式栈（已完成）

None — 信号连接部分已修复，脚本中止逻辑待实现。
