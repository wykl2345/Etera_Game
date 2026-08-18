"""
主窗口管理器 (window_manager.py)

命令行风格的单窗口管理器。
整合 ConsoleWidget（主界面）+ ImageWidget（立绘，可选）。
事件总线连接集中在 ConsoleWidget。

终端风格：暗底亮字，等宽字体，选项嵌入文本。
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QStatusBar, QLabel
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from pathlib import Path
import logging

from Core.gui.status_bar import GameStatusBar

logger = logging.getLogger(__name__)


class WindowManager(QMainWindow):
    """
    终端风格主窗口

    组合 ConsoleWidget + 可选的 ImageWidget。
    通过 UI 模式栈管理状态栏等全局 UI 元素的可见性。
    """

    # UI 模式 → 状态栏可见性（只有 game 模式显示状态栏）
    _MODE_STATUS_BAR: dict[str, bool] = {
        "main_menu":        False,
        "game":             True,
        "settings":         False,
        "save":             False,
        "load":             False,
        "character_detail": False,
    }

    def __init__(
        self,
        event_bus=None,
        resource_base: Path = None,
        resource_manager=None,
        game_context=None,
        restart_callback=None,
        title: str = "Etera_Game"
    ):
        super().__init__()
        self._event_bus = event_bus
        self._resource_base = resource_base or Path("resources")
        self._resource_manager = resource_manager
        self._game_context = game_context
        self._restart_callback = restart_callback
        self._event_connections: list = []

        # UI 模式栈（栈顶 = 当前模式）
        self._mode_stack: list[str] = ["main_menu"]

        self._setup_window(title)
        self._create_widgets()
        self._setup_layout()
        self._create_menu()
        self._connect_events()

        self._apply_mode()  # 应用初始模式（main_menu → 隐藏状态栏）

        logger.info("WindowManager 初始化完成")

    def _setup_window(self, title: str):
        """设置窗口属性"""
        self.setWindowTitle(title)
        self.setMinimumSize(900, 650)
        self.resize(1100, 780)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #0C0C0C;
            }
            QStatusBar {
                background-color: #181818;
                color: #606060;
                font-size: 11px;
                padding: 2px 12px;
                border-top: 1px solid #252525;
            }
        """)

    def _create_widgets(self):
        """创建子组件"""
        from Core.gui.console_widget import ConsoleWidget
        from Core.gui.image_widget import ImageWidget

        self.status_bar_widget = GameStatusBar(
            event_bus=self._event_bus,
            game_context=self._game_context,
            parent=self
        )
        self.console = ConsoleWidget(self._event_bus, self)
        self.image_widget = ImageWidget(
            self._resource_base / "images",
            resource_manager=self._resource_manager,
            parent=self
        )
        self.image_widget.hide()  # 默认隐藏，需要时再显示

    def _setup_layout(self):
        """主布局：状态栏 → 图像区 → 控制台"""
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部状态栏（默认隐藏，游戏开始后显示）
        layout.addWidget(self.status_bar_widget)
        self.status_bar_widget.hide()

        # 图像区（默认隐藏）
        layout.addWidget(self.image_widget, 0)  # stretch=0 收缩到最小

        # 控制台主体
        layout.addWidget(self.console, 1)

        # 底部状态栏（最小化，后续 Phase 2 替换为功能栏）
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("F1 帮助 | Esc 退出")

    def _create_menu(self):
        """菜单栏"""
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background-color: #181818;
                color: #909090;
                border-bottom: 1px solid #252525;
            }
            QMenuBar::item:selected {
                background-color: #303030;
            }
            QMenu {
                background-color: #181818;
                color: #909090;
                border: 1px solid #303030;
            }
            QMenu::item:selected {
                background-color: #303030;
            }
        """)

        game_menu = menubar.addMenu("游戏")
        save_action = QAction("保存 (Ctrl+S)", self)
        save_action.setShortcut("Ctrl+S")
        game_menu.addAction(save_action)

        game_menu.addSeparator()
        restart_action = QAction("重启引擎 (F5)", self)
        restart_action.setShortcut("F5")
        restart_action.triggered.connect(self._on_restart_triggered)
        game_menu.addAction(restart_action)

        quit_action = QAction("退出 (Esc)", self)
        quit_action.setShortcut("Esc")
        quit_action.triggered.connect(self.close)
        game_menu.addAction(quit_action)

        debug_menu = menubar.addMenu("调试")
        clear_action = QAction("清空控制台", self)
        clear_action.triggered.connect(self.console.clear)
        debug_menu.addAction(clear_action)

    def _on_restart_triggered(self):
        """菜单 "重启引擎 F5" 触发"""
        if self._restart_callback:
            self._restart_callback()
        else:
            logger.warning("重启回调未设置，F5 无操作")

    def _connect_events(self):
        """连接事件总线"""
        if not self._event_bus:
            return
        bus = self._event_bus

        subscriptions = [
            ("ui.text_display", self.console.on_text_display),
            ("ui.clear", self.console.on_clear),
            ("ui.choice_show", self.console.on_choice_show),
        ]
        for event_name, callback in subscriptions:
            bus.subscribe(event_name, callback)
            self._event_connections.append((event_name, callback))

        logger.info(f"事件连接完成: {len(self._event_connections)} 个订阅")

    # ─── UI 模式栈 ───────────────────────────────────

    def push_mode(self, mode: str):
        """进入一个 UI 模式，自动更新全局 UI 元素可见性"""
        if mode not in self._MODE_STATUS_BAR:
            logger.warning(f"未知 UI 模式: {mode}，使用 main_menu 回退")
            mode = "main_menu"
        self._mode_stack.append(mode)
        self._apply_mode()
        logger.debug(f"UI 模式入栈: {mode}  |  栈: {' → '.join(self._mode_stack)}")

    def pop_mode(self) -> str | None:
        """退出当前 UI 模式，返回上一级。栈底不可弹出。"""
        if len(self._mode_stack) <= 1:
            logger.warning("无法弹出栈底模式")
            return None
        mode = self._mode_stack.pop()
        self._apply_mode()
        logger.debug(f"UI 模式出栈: {mode}  |  栈: {' → '.join(self._mode_stack)}")
        return mode

    def reset_mode(self, mode: str = "main_menu"):
        """重置到单一模式（重启 / 返回标题画面）"""
        self._mode_stack = [mode]
        self._apply_mode()
        logger.debug(f"UI 模式重置: {mode}")

    def current_mode(self) -> str:
        """获取当前 UI 模式"""
        return self._mode_stack[-1] if self._mode_stack else "main_menu"

    def _apply_mode(self):
        """根据当前模式刷新全局 UI 元素"""
        mode = self.current_mode()
        visible = self._MODE_STATUS_BAR.get(mode, False)
        if visible:
            self.status_bar_widget.show()
            self.status_bar_widget.refresh()
        else:
            self.status_bar_widget.hide()

    # ─── 状态栏（委托方法，保留兼容） ───────────────

    def update_status(self, day: int = None, location: str = None):
        """更新状态栏（委托给 GameStatusBar）"""
        if self.status_bar_widget:
            self.status_bar_widget.refresh()

    def show_status_bar(self):
        """显示顶部状态栏（等效于 push_mode('game')）"""
        self.push_mode("game")

    def hide_status_bar(self):
        """隐藏顶部状态栏（等效于 reset_mode('main_menu')）"""
        self.reset_mode("main_menu")

    def show_image_area(self):
        """显示图像区域（需要时调用）"""
        self.image_widget.show()

    def cleanup(self):
        if self.status_bar_widget:
            self.status_bar_widget.cleanup()
        bus = self._event_bus
        if bus:
            for event_name, callback in self._event_connections:
                try:
                    bus.unsubscribe(event_name, callback)
                except Exception as e:
                    logger.warning(f"移除事件连接失败 {event_name}: {e}")
        self._event_connections.clear()
        logger.info("WindowManager 已清理")

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)
