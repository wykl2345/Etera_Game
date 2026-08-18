#!/usr/bin/env python3
"""
Etera_Game 引擎启动入口

初始化所有核心模块，启动游戏主循环。
遵循开发日志架构设计：
  GUI层 ↔ 引擎核心 ↔ 脚本沙箱层

模块初始化序列封装在 Core.engine.bootstrap.EngineBootstrap 中。

使用方式：
    python Core/main.py

依赖：
    pip install PySide6 lupa pyyaml pygame
"""

import sys
import os
from pathlib import Path
from typing import Optional

# 将项目根目录加入 sys.path，确保 from Core.xxx 导入可用
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
    os.chdir(str(_project_root))  # 同时切换工作目录到项目根

from Core.engine.bootstrap import EngineBootstrap


# ==================== 引擎主类 ====================

class EteraEngine:
    """
    游戏引擎主类

    负责生命周期管理、主菜单循环和 Qt 事件循环。
    模块初始化委托给 EngineBootstrap。
    """

    def __init__(self, debug: bool = False):
        # 启动引导——创建并连接所有模块
        bootstrap = EngineBootstrap(debug=debug)
        bootstrap.initialize()

        # 继承所有模块引用
        self.logger = bootstrap.logger
        self.debug = debug
        self.running = False
        self.event_bus = bootstrap.event_bus
        self.game_context = bootstrap.game_context
        self.save_manager = bootstrap.save_manager
        self.resource_manager = bootstrap.resource_manager
        self.sandbox = bootstrap.sandbox
        self.api_bridge = bootstrap.api_bridge
        self.scheduler = bootstrap.scheduler
        self.character_model = bootstrap.character_model
        self.window = bootstrap.window
        self._qt_app = bootstrap.qt_app
        self._pending_restart: bool = False

        # 连接生命周期事件
        self.event_bus.subscribe("on_game_start", self._on_game_start)
        self.event_bus.subscribe("on_game_end", self._on_game_end)

        # 注入重启回调（WindowManager 的菜单 "重启引擎 F5" 触发）
        if self.window:
            self.window._restart_callback = self._restart_engine

    # ==================== 生命周期事件 ====================

    def _load_characters_into_context(self):
        """将角色模板加载到 GameContext（新游戏/重启时调用）"""
        for char_info in self.character_model.list_characters():
            template = self.character_model.get_template(char_info["id"])
            if template:
                data = self.character_model.apply_template(template)
                self.game_context.add_character(data["id"], data["name"])

    def _on_game_start(self, **kwargs):
        """游戏开始事件（舞台已在 _start_new_game 中搭建完毕）"""
        self.logger.info("游戏开始！")

    def _on_game_end(self, **kwargs):
        """游戏结束事件"""
        self.logger.info("游戏结束")

    # ==================== 主菜单 ====================

    TITLE_ART = r"""
     ______     __
    / ____/__  / /_____ _________
   / __/ / _ \/ __/ __ `/ ___/ _ `/
  / /___/  __/ /_/ /_/ / /  /  __/
 /_____/\___/\__/\__,_/_/   \___/
    """

    def _show_main_menu(self) -> str:
        """显示主菜单并返回玩家选择: start / continue / settings / exit"""
        c = self.window.console
        c.clear()

        # ASCII 标题
        for line in self.TITLE_ART.strip('\n').split('\n'):
            c.write(line, "cyan", True)
        c.write("")
        c.write("  ~ 幻 想 乡 叙 事 引 擎 ~", "yellow")
        c.write("")
        c.write("─" * 52, "dim")
        c.write("")

        # 菜单项
        has_save = self.save_manager.has_quick_save()
        c.write("  [1]  开始新游戏", "menu")
        if has_save:
            c.write("  [2]  继续游戏", "menu")
        else:
            c.write("  [2]  继续游戏  (无存档)", "dim")
        c.write("  [3]  设置", "menu")
        c.write("  [4]  退出游戏", "menu")
        c.write("")
        c.write("─" * 52, "dim")
        c.write("")
        c.write("  ▸ 按数字键选择...", "dim")

        # 激活键盘监听
        c.start_waiting(4)

        # 等待选择（嵌套 QEventLoop）
        # F5 重启时 wait_for_choice() 抛出 ScriptAbortedError
        from Core.engine.script_runner import ScriptAbortedError
        try:
            choice = self.scheduler.wait_for_choice()
        except ScriptAbortedError:
            c.stop_waiting()
            c.write("")
            return "restart"

        c.stop_waiting()
        c.write("")

        if choice == 1:
            return "start"
        elif choice == 2 and has_save:
            return "continue"
        elif choice == 3:
            return "settings"
        else:
            return "exit"

    def _show_settings_menu(self):
        """显示设置菜单"""
        self.window.push_mode("settings")
        try:
            c = self.window.console
            c.clear()
            c.write("", "white")
            c.write("  ═══ 设  置 ═══", "cyan", True)
            c.write("")
            c.write("  游戏设置（敬请期待）", "dim")
            c.write("")
            c.write("  [1]  返回主菜单", "menu")
            c.write("")
            c.start_waiting(1)
            choice = self.scheduler.wait_for_choice()
            c.stop_waiting()
            if choice == 1:
                return
        finally:
            self.window.pop_mode()

    # ==================== 启动与运行 ====================

    def run(self):
        """启动引擎主循环（支持重启回到主菜单）"""
        if self.running:
            self.logger.warning("引擎已在运行中")
            return

        self.running = True
        self.window.show()

        # ── 主循环：菜单 ↔ 游戏会话 ──
        while self.running:
            action = self._show_main_menu()

            if action == "restart":
                # F5 在主菜单被按下，重新显示菜单
                continue
            elif action == "start":
                self._start_new_game()
            elif action == "continue":
                if self.save_manager.quick_load():
                    self.window.console.write("  存档已加载。", "green")
                    self.window.show_status_bar()
                    self._qt_app.exec()
                else:
                    self.window.console.write("  加载存档失败。", "red")
                    continue
            elif action == "settings":
                self._show_settings_menu()
                continue
            elif action == "exit":
                self.window.console.write("  再见。", "dim")
                self.window.close()
                self.running = False
                break

            # 进入 Qt 事件循环（游戏会话）
            # F5 重启时 _restart_engine 设置 _pending_restart + quit()
            # 窗口关闭时 exec() 返回后窗口不可见
            self._qt_app.exec()

            if self._pending_restart:
                self._pending_restart = False
                continue  # 回到主菜单

            # 窗口被直接关闭（X 按钮）→ 退出
            if not self.window.isVisible():
                self.running = False
                break

        self.cleanup()
        sys.exit(0)

    def _start_new_game(self):
        """开始新游戏 — 舞台搭建 → 通知脚本"""
        self.window.console.write("")
        self.window.console.write("  正在进入幻想乡...", "green")
        self.window.console.write("")

        # 舞台搭建（脚本运行前必须完成）
        self.save_manager.start_session()
        self._load_characters_into_context()
        if self.window:
            self.window.show_status_bar()

        # 通知脚本：舞台就绪
        self.event_bus.emit("on_game_start")
        self.logger.info("引擎主循环启动完毕")

    def _restart_engine(self):
        """重启引擎：清理当前会话，返回主菜单"""
        self.logger.info("正在重启引擎...")

        # 1. 停止所有脚本（设置 _aborted 标志，退出嵌套等待循环）
        if self.scheduler:
            self.scheduler.stop_all()

        # 2. 发射游戏结束事件
        self.event_bus.emit("on_game_end")

        # 3. 重置游戏状态
        self.game_context.reset()
        self._load_characters_into_context()

        # 4. 隐藏状态栏、清空控制台
        if self.window:
            self.window.hide_status_bar()
            self.window.console.clear()

        # 5. 设置重启标志 + 退出 Qt 事件循环
        #    run() 检测到 _pending_restart 后回到主菜单
        #    使用标志而非依赖 isVisible() 避免 Bug 3（F5 后窗口关闭）
        self._pending_restart = True
        if self._qt_app:
            self._qt_app.quit()

        self.logger.info("引擎已返回主菜单")

    def cleanup(self):
        """清理所有模块"""
        self.logger.info("正在关闭引擎...")

        if self.window:
            self.window.cleanup()
        if self.scheduler:
            self.scheduler.cleanup()
        if self.resource_manager:
            self.resource_manager.clear_cache()
        if self.sandbox:
            self.sandbox.cleanup()

        self.event_bus.emit("on_game_end")
        self.logger.info("引擎已关闭")


# ==================== 入口 ====================

def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description="Etera_Game 游戏引擎")
    parser.add_argument("--debug", action="store_true", help="启用调试模式")
    args = parser.parse_args()

    # 创建并启动引擎（初始化在 __init__ 中通过 EngineBootstrap 完成）
    engine = EteraEngine(debug=args.debug)
    engine.run()


if __name__ == "__main__":
    main()
