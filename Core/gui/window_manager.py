"""
主窗口管理器 (window_manager.py)

整合 LogWidget、ChoiceWidget、ImageWidget 三个子组件，
管理场景布局和主题配置。

与设计文档对应：
- 主窗口管理
- 布局组合：Log + Choice + Image
- 信号连接：从事件总线到各Widget
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QStatusBar, QLabel
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QAction
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class WindowManager(QMainWindow):
    """
    主窗口管理器

    组合三个核心组件，管理整体布局和主题配置。
    连接事件总线到各个Widget的事件处理入口。
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
        self.setMinimumSize(960, 720)
        self.resize(1280, 800)

        # 设置窗口样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a2e;
            }
            QSplitter::handle {
                background-color: #0f3460;
                width: 2px;
            }
            QStatusBar {
                background-color: #0f3460;
                color: #888;
                font-size: 12px;
                padding: 2px 10px;
            }
        """)

    def _create_widgets(self):
        """创建子组件"""
        # 延迟导入避免循环依赖
        from .log_widget import LogWidget
        from .choice_widget import ChoiceWidget
        from .image_widget import ImageWidget

        self.log_widget = LogWidget(self)
        self.choice_widget = ChoiceWidget(self._event_bus, self)
        self.image_widget = ImageWidget(self._resource_base / "images", self)

    def _setup_layout(self):
        """设置主布局"""
        central = QWidget()
        self.setCentralWidget(central)

        # 主布局：上下结构
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 上半部分：图片区
        main_layout.addWidget(self.image_widget, 3)

        # 下半部分：日志区 + 选项区（用分割线分隔）
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)

        bottom_layout.addWidget(self.log_widget, 2)
        bottom_layout.addWidget(self.choice_widget, 1)

        main_layout.addWidget(bottom_widget, 2)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._day_label = QLabel("Day 1")
        self._location_label = QLabel("Home")
        self.status_bar.addPermanentWidget(self._day_label)
        self.status_bar.addPermanentWidget(self._location_label)

    def _create_menu(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background-color: #16213e;
                color: #e0e0e0;
                border-bottom: 1px solid #0f3460;
            }
            QMenuBar::item:selected {
                background-color: #0f3460;
            }
            QMenu {
                background-color: #16213e;
                color: #e0e0e0;
                border: 1px solid #0f3460;
            }
            QMenu::item:selected {
                background-color: #0f3460;
            }
        """)

        # 游戏菜单
        game_menu = menubar.addMenu("游戏")
        save_action = QAction("保存", self)
        save_action.setShortcut("Ctrl+S")
        game_menu.addAction(save_action)

        load_action = QAction("读取", self)
        load_action.setShortcut("Ctrl+L")
        game_menu.addAction(load_action)

        game_menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.setShortcut("Esc")
        quit_action.triggered.connect(self.close)
        game_menu.addAction(quit_action)

        # 调试菜单
        debug_menu = menubar.addMenu("调试")
        clear_log_action = QAction("清空日志", self)
        clear_log_action.triggered.connect(self.log_widget.clear_text)
        debug_menu.addAction(clear_log_action)

    def _connect_events(self):
        """连接事件总线到各Widget"""
        if not self._event_bus:
            logger.warning("事件总线未设置，跳过事件连接")
            return

        bus = self._event_bus

        # LogWidget 事件
        self._event_connections.extend([
            bus.subscribe("ui.text_display", self.log_widget.on_text_display),
            bus.subscribe("ui.clear", self.log_widget.on_clear),
        ])

        # ChoiceWidget 事件
        self._event_connections.extend([
            bus.subscribe("ui.choice_show", self.choice_widget.on_choice_show),
        ])

        # ImageWidget 事件
        self._event_connections.extend([
            bus.subscribe("ui.image_show", self.image_widget.on_image_show),
            bus.subscribe("ui.image_hide", self.image_widget.on_image_hide),
            bus.subscribe("ui.character_show", self.image_widget.on_character_show),
            bus.subscribe("ui.character_hide", self.image_widget.on_character_hide),
            bus.subscribe("ui.background_set", self.image_widget.on_background_set),
        ])

        # 状态栏更新事件
        self._event_connections.extend([
            bus.subscribe("on_day_begin", self._on_day_begin),
            bus.subscribe("on_location_change", self._on_location_change),
        ])

        logger.info(f"事件连接完成: {len(self._event_connections)} 个订阅")

    def _on_day_begin(self, day: int, **kwargs):
        """更新状态栏天数"""
        self._day_label.setText(f"Day {day}")

    def _on_location_change(self, location: str, **kwargs):
        """更新状态栏位置"""
        self._location_label.setText(location)

    def update_status(self, day: int = None, location: str = None):
        """手动更新状态栏"""
        if day is not None:
            self._day_label.setText(f"Day {day}")
        if location is not None:
            self._location_label.setText(location)

    def cleanup(self):
        """清理事件连接和资源"""
        for unsubscribe in self._event_connections:
            try:
                unsubscribe()
            except Exception as e:
                logger.warning(f"移除事件连接失败: {e}")
        self._event_connections.clear()
        logger.info("WindowManager 已清理")

    def closeEvent(self, event):
        """窗口关闭事件"""
        self.cleanup()
        super().closeEvent(event)
