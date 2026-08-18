"""
ScriptScheduler 单元测试 — Issue 2: F5 重启引擎修复

覆盖：ScriptAbortedError、stop_all 中止标志、wait_for_choice/input 中止检测、
      正常流程回归、resolve_wait 幂等、run_script_sync 的 abort 处理。
"""

import pytest
from unittest.mock import MagicMock

from Core.engine.script_runner import ScriptScheduler


# ─── 辅助 fixtures ─────────────────────────────────────

@pytest.fixture
def mock_event_bus():
    """返回带 subscribe/unsubscribe/emit 的 mock 事件总线"""
    bus = MagicMock()
    bus.subscribe.return_value = MagicMock()  # 返回可调用的 unsubscribe
    return bus


@pytest.fixture
def mock_sandbox():
    """返回 mock Lua 沙箱"""
    return MagicMock()


@pytest.fixture
def mock_context():
    """返回 mock 游戏上下文"""
    return MagicMock()


@pytest.fixture
def scheduler(mock_event_bus, mock_sandbox, mock_context):
    """创建可用于测试的 ScriptScheduler"""
    return ScriptScheduler(
        event_bus=mock_event_bus,
        sandbox=mock_sandbox,
        game_context=mock_context,
    )


# ─── Test 1: ScriptAbortedError 存在 ──────────────────

def test_script_aborted_error_is_exception():
    """ScriptAbortedError 应该是 Exception 的子类"""
    from Core.engine.script_runner import ScriptAbortedError
    assert issubclass(ScriptAbortedError, Exception)


# ─── Test 2: stop_all() 设置 _aborted 标志 ─────────────

def test_stop_all_sets_aborted_flag(scheduler):
    """stop_all() 应将 _aborted 设为 True"""
    assert scheduler._aborted is False
    scheduler.stop_all()
    assert scheduler._aborted is True


# ─── Test 3: stop_all() 空闲时不崩溃 ───────────────────

def test_stop_all_when_idle_no_error(scheduler):
    """stop_all() 在无活动等待循环时不应抛出异常"""
    scheduler.stop_all()  # 空闲状态
    scheduler.stop_all()  # 重复调用也应安全
    assert scheduler._aborted is True


# ─── Test 4: wait_for_choice() 中止时 raise ────────────

def test_wait_for_choice_raises_when_aborted(scheduler):
    """_aborted=True 时 wait_for_choice() 应立即抛出 ScriptAbortedError"""
    from Core.engine.script_runner import ScriptAbortedError
    scheduler.stop_all()  # 设置 _aborted = True
    with pytest.raises(ScriptAbortedError):
        scheduler.wait_for_choice()


# ─── Test 5: wait_for_input() 中止时 raise ─────────────

def test_wait_for_input_raises_when_aborted(scheduler):
    """_aborted=True 时 wait_for_input() 应立即抛出 ScriptAbortedError"""
    from Core.engine.script_runner import ScriptAbortedError
    scheduler.stop_all()
    with pytest.raises(ScriptAbortedError):
        scheduler.wait_for_input()


# ─── Test 6: 正常 wait_for_choice() 回归 ───────────────
# 需要 QApplication + QTimer

def test_wait_for_choice_normal_flow(scheduler, qapp):
    """正常流程：resolve 后 wait_for_choice() 返回正确索引"""
    from PySide6.QtCore import QTimer

    # 50ms 后 resolve 选择 2
    QTimer.singleShot(50, lambda: scheduler.resolve_wait(choice_index=2))
    result = scheduler.wait_for_choice()
    assert result == 2
    assert scheduler._aborted is False


# ─── Test 7: stop_all 在等待期间 raise ─────────────────

def test_stop_all_during_wait_for_choice_raises(scheduler, qapp):
    """在 wait_for_choice() 阻塞期间 stop_all() → 应抛出 ScriptAbortedError"""
    from Core.engine.script_runner import ScriptAbortedError
    from PySide6.QtCore import QTimer

    # 50ms 后调用 stop_all() 模拟 F5
    QTimer.singleShot(50, lambda: scheduler.stop_all())
    with pytest.raises(ScriptAbortedError):
        scheduler.wait_for_choice()


# ─── Test 8: resolve_wait 在 abort 后幂等 ──────────────

def test_resolve_wait_after_abort_returns_false(scheduler):
    """stop_all() 后 resolve_wait() 应返回 False（活动循环已退出）"""
    scheduler.stop_all()
    assert scheduler.resolve_wait(choice_index=1) is False


# ─── Test 9: run_script_sync 捕获 abort ────────────────

def test_run_script_sync_catches_abort(scheduler, mock_sandbox, tmp_path):
    """run_script_sync() 应捕获 ScriptAbortedError 并 emit script.aborted"""
    from Core.engine.script_runner import ScriptAbortedError

    # 创建一个临时 Lua 文件
    lua_file = tmp_path / "test_abort.lua"
    lua_file.write_text("ui.text('hello')", encoding="utf-8")

    # Mock sandbox：execute 时抛出 ScriptAbortedError（模拟 F5 中断）
    mock_runtime = mock_sandbox.get_runtime.return_value
    mock_runtime.execute.side_effect = ScriptAbortedError("aborted during test")

    # Mock _resolve_script_path 让它返回我们的临时文件
    scheduler._resolve_script_path = lambda p: str(lua_file)

    result = scheduler.run_script_sync("test_abort.lua")

    # 应返回 False（脚本未正常完成）
    assert result is False

    # 应 emit script.aborted 而非 script.error
    aborted_calls = [
        c for c in scheduler.event_bus.emit.call_args_list
        if c[0][0] == "script.aborted"
    ]
    error_calls = [
        c for c in scheduler.event_bus.emit.call_args_list
        if c[0][0] == "script.error"
    ]
    assert len(aborted_calls) >= 1, "应 emit script.aborted 事件"
    assert len(error_calls) == 0, "不应 emit script.error 事件"
