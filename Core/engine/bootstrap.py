"""
引擎启动引导模块 (bootstrap.py)

封装 Etera_Game 引擎的完整初始化序列。
从 main.py 提取，减少 EteraEngine 的职责范围。

初始化顺序（有向依赖）:
  EventBus → GameContext → CharacterModel → ResourceManager
  → SaveManager → LuaSandbox → LuaAPI → ScriptScheduler
  → GUI(WindowManager) → Event Scripts

产物通过属性访问，供 EteraEngine 消费。
"""

import sys
import logging
from pathlib import Path


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


class EngineBootstrap:
    """
    引擎启动引导器

    按依赖顺序初始化所有核心模块。
    调用 initialize() 后，通过属性访问各模块实例。

    使用示例：
        bootstrap = EngineBootstrap(debug=False)
        bootstrap.initialize()
        # 使用 bootstrap.event_bus, bootstrap.game_context, ...
    """

    def __init__(self, debug: bool = False):
        self.logger = setup_logging(debug)
        self.debug = debug

        # 产物
        self.event_bus = None
        self.game_context = None
        self.character_model = None
        self.resource_manager = None
        self.save_manager = None
        self.sandbox = None
        self.api_bridge = None
        self.scheduler = None
        self.window = None
        self.qt_app = None

        self.logger.info("=" * 50)
        self.logger.info("Etera_Game 引擎启动中...")
        self.logger.info("=" * 50)

    def initialize(self) -> "EngineBootstrap":
        """按依赖顺序初始化所有模块"""
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

    # ─── 初始化步骤 ─────────────────────────────────────

    def _init_event_bus(self):
        from Core.engine.event_bus import EventBus
        self.event_bus = EventBus()
        self.logger.info("[✓] 事件总线")

    def _init_game_context(self):
        from Core.state.game_context import GameContext
        self.game_context = GameContext()
        self.logger.info("[✓] 游戏上下文")

    def _init_character_model(self):
        from Core.state.character_model import CharacterModel
        self.character_model = CharacterModel(Path("data/characters"))
        loaded = self.character_model.load_all()
        self.logger.info(f"[✓] 角色数据模型（{len(loaded)} 个角色）")

    def _init_resource_manager(self):
        from Core.resource.resource_manager import ResourceManager
        self.resource_manager = ResourceManager(
            base_dir=Path("resources"),
        )
        self.logger.info("[✓] 资源管理器")

    def _init_save_manager(self):
        from Core.state.save_manager import SaveManager
        self.save_manager = SaveManager(
            event_bus=self.event_bus,
            game_context=self.game_context,
            base_dir=Path("saves")
        )
        self.logger.info("[✓] 存档管理器")

    def _init_sandbox(self):
        from Core.engine.sandbox import LuaSandbox
        self.sandbox = LuaSandbox()
        self.logger.info("[✓] Lua 沙箱")

    def _init_api_bridge(self):
        from Core.engine.api_bridge import LuaAPI
        self.api_bridge = LuaAPI(
            scheduler=self,        # 暂用 self，scheduler 初始化后会替换
            context=self.game_context,
            event_bus=self.event_bus,
            resource_manager=self.resource_manager,
        )
        self.logger.info("[✓] API 桥接器")

    def _init_scheduler(self):
        from Core.engine.script_runner import ScriptScheduler
        self.scheduler = ScriptScheduler(
            event_bus=self.event_bus,
            sandbox=self.sandbox,
            game_context=self.game_context,
        )
        # 修正 API bridge 中的 scheduler 引用
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
        from PySide6.QtWidgets import QApplication

        # 创建 Qt 应用（如果还没有）
        self.qt_app = QApplication.instance()
        if not self.qt_app:
            self.qt_app = QApplication(sys.argv)
            self.qt_app.setApplicationName("Etera_Game")

        # 创建主窗口（不连接生命周期事件——由 EteraEngine 负责）
        from Core.gui.window_manager import WindowManager
        self.window = WindowManager(
            event_bus=self.event_bus,
            resource_base=Path("resources"),
            resource_manager=self.resource_manager,
            game_context=self.game_context,
            title="Etera_Game - 游戏引擎"
        )
        # restart_callback 由 EteraEngine 在 __init__ 中设置
        # （需要在 main.py 中 self.window._restart_callback = self._restart_engine）

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

                result = lua.execute(code)

                if result is None:
                    self.logger.warning(f"脚本未返回 table，跳过: {filepath}")
                    continue

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

                rel_path = filepath.relative_to(events_dir)
                self.logger.info(f"  注册事件: {on_event} ← {rel_path}")
                self.event_bus.subscribe(on_event, execute_fn)
                loaded_count += 1

            except Exception as e:
                rel_path = filepath.relative_to(events_dir) if filepath.is_relative_to(events_dir) else filepath.name
                self.logger.error(f"加载事件脚本失败 {rel_path}: {e}")

        self.logger.info(f"[✓] 事件脚本加载完成: {loaded_count}/{len(lua_files)}")
