#!/usr/bin/env python3
"""
Etera_Game 引擎启动入口

初始化所有核心模块，启动游戏主循环。
遵循开发日志架构设计：
  GUI层 ↔ 引擎核心 ↔ 脚本沙箱层

使用方式：
    python Core/main.py

依赖：
    pip install PySide6 lupa pyyaml pygame
"""

import sys
import os
import logging
from pathlib import Path
from typing import Optional

# 将项目根目录加入 sys.path，确保 from Core.xxx 导入可用
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
    os.chdir(str(_project_root))  # 同时切换工作目录到项目根

# ==================== 日志配置 ====================

def setup_logging(debug: bool = False):
    """配置日志系统"""
    level = logging.DEBUG if debug else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )

    # 关闭第三方库的冗余日志
    logging.getLogger("PySide6").setLevel(logging.WARNING)
    logging.getLogger("lupa").setLevel(logging.WARNING)

    return logging.getLogger("EteraGame")


# ==================== 引擎初始化 ====================

class EteraEngine:
    """
    游戏引擎主类

    负责所有模块的初始化、连接和生命周期管理。
    """

    def __init__(self, debug: bool = False):
        self.logger = setup_logging(debug)
        self.debug = debug
        self.running = False

        # 模块引用（初始化时填充）
        self.event_bus = None
        self.game_context = None
        self.save_manager = None
        self.resource_manager = None
        self.sandbox = None
        self.api_bridge = None
        self.scheduler = None
        self.character_model = None
        self.window = None

        self.logger.info("=" * 50)
        self.logger.info("Etera_Game 引擎启动中...")
        self.logger.info("=" * 50)

    def initialize(self):
        """初始化所有模块"""
        self._init_event_bus()
        self._init_game_context()
        self._init_character_model()
        self._init_resource_manager()
        self._init_save_manager()
        self._init_sandbox()
        self._init_api_bridge()
        self._init_scheduler()
        self._init_gui()
        self._load_event_scripts()

        self.logger.info("所有模块初始化完成！")
        return self

    def _init_event_bus(self):
        """初始化事件总线"""
        from Core.engine.event_bus import EventBus
        self.event_bus = EventBus()
        self.logger.info("[✓] 事件总线")

    def _init_game_context(self):
        """初始化游戏上下文"""
        from Core.state.game_context import GameContext
        self.game_context = GameContext()
        self.logger.info("[✓] 游戏上下文")

    def _init_character_model(self):
        """初始化角色数据模型"""
        from Core.state.character_model import CharacterModel
        self.character_model = CharacterModel(Path("data/characters"))
        loaded = self.character_model.load_all()
        self.logger.info(f"[✓] 角色数据模型（{len(loaded)} 个角色）")

    def _init_resource_manager(self):
        """初始化资源管理器"""
        from Core.resource.resource_manager import ResourceManager
        from Core.resource.cache import LRUCache
        self.resource_manager = ResourceManager(
            base_dir=Path("resources"),
        )
        self.logger.info("[✓] 资源管理器")

    def _init_save_manager(self):
        """初始化存档管理器"""
        from Core.state.save_manager import SaveManager
        self.save_manager = SaveManager(
            event_bus=self.event_bus,
            game_context=self.game_context,
            base_dir=Path("saves")
        )
        self.logger.info("[✓] 存档管理器")

    def _init_sandbox(self):
        """初始化 Lua 沙箱"""
        from Core.engine.sandbox import LuaSandbox
        self.sandbox = LuaSandbox()
        self.logger.info("[✓] Lua 沙箱")

    def _init_api_bridge(self):
        """初始化 API 桥接器"""
        from Core.engine.api_bridge import LuaAPI
        self.api_bridge = LuaAPI(
            scheduler=self,        # 暂用 self，scheduler 初始化后会替换
            context=self.game_context,
            event_bus=self.event_bus,
            resource_manager=self.resource_manager,
        )
        self.logger.info("[✓] API 桥接器")

    def _init_scheduler(self):
        """初始化脚本调度器"""
        from Core.engine.script_runner import ScriptScheduler
        self.scheduler = ScriptScheduler(
            event_bus=self.event_bus,
            sandbox=self.sandbox,
            game_context=self.game_context,
        )
        # 更新 API bridge 中的 scheduler 引用
        self.api_bridge.scheduler = self.scheduler

        # 将 API 注入沙箱
        env = self.api_bridge.build_env()
        lua = self.sandbox.get_runtime()
        if lua:
            for name, value in env.items():
                try:
                    lua.globals()[name] = value
                    self.logger.debug(f"  注入 API: {name}")
                except Exception as e:
                    self.logger.warning(f"  注入 API 失败 {name}: {e}")

        self.logger.info("[✓] 脚本调度器 + API 注入")

    def _init_gui(self):
        """初始化 GUI"""
        from PySide6.QtWidgets import QApplication

        # 创建 Qt 应用（如果还没有）
        self._qt_app = QApplication.instance()
        if not self._qt_app:
            self._qt_app = QApplication(sys.argv)
            self._qt_app.setApplicationName("Etera_Game")

        # 创建主窗口
        from Core.gui.window_manager import WindowManager
        self.window = WindowManager(
            event_bus=self.event_bus,
            resource_base=Path("resources"),
            title="Etera_Game - 游戏引擎"
        )

        # 连接存档管理器的事件
        self.event_bus.subscribe("on_game_start", self._on_game_start)
        self.event_bus.subscribe("on_game_end", self._on_game_end)

        self.logger.info("[✓] GUI 主窗口")

    def _load_event_scripts(self):
        """扫描 data/events/ 目录，加载所有 Lua 事件脚本并注册到事件总线"""
        events_dir = Path("data/events")
        if not events_dir.exists():
            self.logger.warning("事件脚本目录不存在: data/events/")
            return

        lua_files = list(events_dir.rglob("*.lua"))
        if not lua_files:
            self.logger.warning("未找到任何 .lua 事件脚本")
            return

        lua = self.sandbox.get_runtime()
        if not lua:
            self.logger.warning("Lua 运行时不可用，跳过事件加载")
            return

        loaded_count = 0
        for filepath in lua_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    code = f.read()

                # 执行脚本，获取返回的 table {on_event, execute}
                result = lua.execute(code)

                if result is None:
                    self.logger.warning(f"脚本未返回 table，跳过: {filepath}")
                    continue

                # lupa 返回 _LuaTable，不支持 .get()，用 [] 或属性访问
                try:
                    on_event = result["on_event"]
                    execute_fn = result["execute"]
                except (KeyError, TypeError):
                    try:
                        on_event = result.on_event
                        execute_fn = result.execute
                    except AttributeError:
                        self.logger.warning(f"脚本返回格式无效（缺少 on_event/execute）: {filepath}")
                        continue

                if not on_event or not execute_fn:
                    self.logger.warning(f"脚本缺少 on_event/execute: {filepath}")
                    continue

                # 注册到事件总线
                rel_path = filepath.relative_to(events_dir)
                self.logger.info(f"  注册事件: {on_event} ← {rel_path}")

                self.event_bus.subscribe(on_event, execute_fn)
                loaded_count += 1

            except Exception as e:
                rel_path = filepath.relative_to(events_dir) if filepath.is_relative_to(events_dir) else filepath.name
                self.logger.error(f"加载事件脚本失败 {rel_path}: {e}")

        self.logger.info(f"[✓] 事件脚本加载完成: {loaded_count}/{len(lua_files)}")

    # ==================== 生命周期事件 ====================

    def _on_game_start(self, **kwargs):
        """游戏开始事件"""
        self.logger.info("游戏开始！")
        self.save_manager.start_session()

        # 加载角色数据到上下文
        for char_id in self.character_model.list_characters():
            template = self.character_model.get_template(char_id["id"])
            if template:
                data = self.character_model.apply_template(template)
                self.game_context.add_character(data["id"], data["name"])

        # 更新 GUI 状态栏
        if self.window:
            self.window.update_status(
                day=self.game_context.get_day(),
                location=self.game_context.get_location()
            )

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
        choice = self.scheduler.wait_for_choice()
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

    # ==================== 启动与运行 ====================

    def run(self):
        """启动引擎主循环"""
        if self.running:
            self.logger.warning("引擎已在运行中")
            return

        self.running = True

        # 显示窗口
        self.window.show()

        # ── 主菜单循环 ──
        while True:
            action = self._show_main_menu()

            if action == "start":
                # 开始新游戏
                self.window.console.write("")
                self.window.console.write("  正在进入幻想乡...", "green")
                self.window.console.write("")

                # 触发游戏开始
                self.event_bus.emit("on_game_start")
                break  # 进入 Qt 事件循环

            elif action == "continue":
                if self.save_manager.quick_load():
                    self.window.console.write("  存档已加载。", "green")
                else:
                    self.window.console.write("  加载存档失败。", "red")
                continue  # 回到主菜单

            elif action == "settings":
                self._show_settings_menu()
                continue

            elif action == "exit":
                self.window.console.write("  再见。", "dim")
                self.window.close()
                return

        self.logger.info("引擎主循环启动完毕")

        # 进入 Qt 事件循环
        exit_code = self._qt_app.exec()
        self.running = False

        # 清理
        self.cleanup()

        sys.exit(exit_code)

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

    # 创建并启动引擎
    engine = EteraEngine(debug=args.debug)
    engine.initialize()
    engine.run()


if __name__ == "__main__":
    main()
