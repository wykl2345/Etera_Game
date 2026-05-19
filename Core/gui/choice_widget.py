"""
选项按钮组件 (choice_widget.py)

显示选择菜单，接收 ui.choice_show 事件并生成按钮。
玩家点击后通过事件总线发射 ui.choice_made 事件。

与设计文档对应：
- 接收 ask_choice() 调用 → 生成按钮
- 用户点击 → 恢复脚本执行
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QScrollArea
)
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont
import logging

logger = logging.getLogger(__name__)


class ChoiceButton(QPushButton):
    """单个选项按钮（带悬停动画）"""

    def __init__(self, text: str, index: int, parent=None):
        super().__init__(text, parent)
        self.index = index
        self._setup_style()
        self._anim = QPropertyAnimation(self, b"maximumHeight")
        self._anim.setDuration(150)
        logger.debug(f"ChoiceButton 创建: [{index}] {text[:20]}...")

    def _setup_style(self):
        """设置按钮样式"""
        self.setMinimumHeight(48)
        self.setMaximumHeight(48)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QPushButton {
                background-color: #16213e;
                color: #e0e0e0;
                border: 1px solid #0f3460;
                border-radius: 8px;
                padding: 12px 20px;
                font-size: 14px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #0f3460;
                border-color: #e94560;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #e94560;
                color: #ffffff;
            }
        """)
        font = QFont("Microsoft YaHei", 11)
        self.setFont(font)


class ChoiceWidget(QWidget):
    """选项菜单组件"""

    choice_made = Signal(int)  # 发射选项索引

    def __init__(self, event_bus=None, parent=None):
        super().__init__(parent)
        self._event_bus = event_bus
        self._setup_ui()
        self._buttons: list[ChoiceButton] = []
        self._active = False
        logger.info("ChoiceWidget 初始化完成" + (" (event_bus已连接)" if event_bus else ""))

    def _setup_ui(self):
        """初始化UI"""
        # 外层滚动区域
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #0f3460;
                border-radius: 3px;
            }
        """)

        # 按钮容器
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setSpacing(8)
        self._layout.setContentsMargins(20, 10, 20, 10)
        self._layout.addStretch()  # 按钮从底部排列

        scroll.setWidget(self._container)

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll)

        # 默认隐藏
        self.hide()

    def show_choices(self, options: list[str]):
        """
        显示选择菜单

        Args:
            options: 选项文本列表
        """
        # 清除旧按钮
        self._clear_buttons()

        # 从布局中移除stretch，添加按钮后再加回去
        self._layout.removeItem(self._layout.itemAt(self._layout.count() - 1))

        # 创建新按钮
        self._buttons = []
        for i, option_text in enumerate(options, 1):
            btn = ChoiceButton(f"  {option_text}", i)
            btn.clicked.connect(lambda checked, idx=i: self._on_choice(idx))
            self._layout.addWidget(btn)
            self._buttons.append(btn)

        self._layout.addStretch()
        self._active = True
        self.show()

        logger.info(f"显示选择菜单: {len(options)} 个选项")

    def hide_choices(self):
        """隐藏选择菜单"""
        self._clear_buttons()
        self._active = False
        self.hide()

    def _on_choice(self, index: int):
        """玩家点击了选项"""
        if not self._active:
            return

        logger.info(f"玩家选择了选项: {index}")
        self._active = False
        self.choice_made.emit(index)

        # 发射事件总线事件（使用传入的实例，而非创建新实例）
        if self._event_bus:
            self._event_bus.emit("ui.choice_made", choice_index=index)
        else:
            logger.warning("ChoiceWidget: event_bus 未设置，无法发射 choice_made 事件")

        # 延迟隐藏（让玩家看到点击反馈）
        from PySide6.QtCore import QTimer
        QTimer.singleShot(200, self.hide_choices)

    def _clear_buttons(self):
        """清除所有按钮"""
        for btn in self._buttons:
            self._layout.removeWidget(btn)
            btn.deleteLater()
        self._buttons.clear()

    def is_active(self) -> bool:
        """是否有选项正在显示"""
        return self._active

    # ==================== 事件总线接口 ====================

    def on_choice_show(self, options: list[str], **kwargs):
        """事件总线回调：显示选择菜单"""
        self.show_choices(options)
