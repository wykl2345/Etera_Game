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

logger = logging.getLogger(__name__)


class WindowManager(QMainWindow):
    """
    终端风格主窗口

    组合 ConsoleWidget + 可选的 ImageWidget。
    """

    def __init__(
        self,
        event_bus=None,
        resource_base: Path = None,
        title: str = "Etera_Game"
    ):
        super().__init__()
        self._event_bus = event_bus
        self._resource_base = resource_base or Path("resources")
        self._event_connections: list = []

        self._setup_window(title)
        self._create_widgets()
        self._setup_layout()
        self._create_menu()
        self._connect_events()

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

        self.console = ConsoleWidget(self._event_bus, self)
        self.image_widget = ImageWidget(self._resource_base / "images", self)
        self.image_widget.hide()  # 默认隐藏，需要时再显示

    def _setup_layout(self):
        """主布局：图像区 + 控制台"""
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 图像区（默认隐藏）
        layout.addWidget(self.image_widget, 0)  # stretch=0 收缩到最小

        # 控制台主体
        layout.addWidget(self.console, 1)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._day_label = QLabel("")
        self._location_label = QLabel("")
        self.status_bar.addPermanentWidget(self._day_label)
        self.status_bar.addPermanentWidget(self._location_label)

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
        quit_action = QAction("退出 (Esc)", self)
        quit_action.setShortcut("Esc")
        quit_action.triggered.connect(self.close)
        game_menu.addAction(quit_action)

        debug_menu = menubar.addMenu("调试")
        clear_action = QAction("清空控制台", self)
        clear_action.triggered.connect(self.console.clear)
        debug_menu.addAction(clear_action)

    def _connect_events(self):
        """连接事件总线"""
        if not self._event_bus:
            return
        bus = self._event_bus

        self._event_connections.extend([
            bus.subscribe("ui.text_display", self.console.on_text_display),
            bus.subscribe("ui.clear", self.console.on_clear),
            bus.subscribe("ui.choice_show", self.console.on_choice_show),
        ])

        # 状态栏
        self._event_connections.extend([
            bus.subscribe("on_day_begin", self._on_day_begin),
            bus.subscribe("on_location_change", self._on_location_change),
        ])

        logger.info(f"事件连接完成: {len(self._event_connections)} 个订阅")

    def _on_day_begin(self, day: int, **kwargs):
        self._day_label.setText(f"Day {day}")

    def _on_location_change(self, location: str, **kwargs):
        self._location_label.setText(location)

    def update_status(self, day: int = None, location: str = None):
        if day is not None:
            self._day_label.setText(f"Day {day}")
        if location is not None:
            self._location_label.setText(location)

    def show_image_area(self):
        """显示图像区域（需要时调用）"""
        self.image_widget.show()

    def cleanup(self):
        for unsubscribe in self._event_connections:
            try:
                unsubscribe()
            except Exception as e:
                logger.warning(f"移除事件连接失败: {e}")
        self._event_connections.clear()
        logger.info("WindowManager 已清理")

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)
