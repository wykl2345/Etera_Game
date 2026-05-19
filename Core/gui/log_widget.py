"""
文本日志显示组件 (log_widget.py)

显示游戏文字内容，支持颜色和粗体渲染。
通过事件总线接收 ui.text_display 和 ui.clear 事件。

与设计文档对应：
- 接收 show_text() 调用 → emit 信号 → 显示文字
- 支持文字颜色、粗体等格式
"""

from PySide6.QtWidgets import QTextBrowser, QWidget, QVBoxLayout
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QTextCursor, QColor, QFont
import logging

logger = logging.getLogger(__name__)

# 颜色名称 → QColor 映射
COLOR_MAP = {
    "white": QColor("#FFFFFF"),
    "red": QColor("#FF4444"),
    "green": QColor("#44FF44"),
    "blue": QColor("#4488FF"),
    "yellow": QColor("#FFFF44"),
    "cyan": QColor("#44FFFF"),
    "magenta": QColor("#FF44FF"),
    "pink": QColor("#FF88C8"),
    "gray": QColor("#888888"),
    "black": QColor("#000000"),
}


class LogWidget(QWidget):
    """文本日志显示组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._text_history: list[str] = []
        logger.info("LogWidget 初始化完成")

    def _setup_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.text_browser = QTextBrowser(self)
        self.text_browser.setReadOnly(True)
        self.text_browser.setOpenExternalLinks(False)
        self.text_browser.setStyleSheet("""
            QTextBrowser {
                background-color: #1a1a2e;
                color: #ffffff;
                border: none;
                padding: 16px;
                font-size: 16px;
            }
        """)

        # 设置默认字体
        font = QFont("Microsoft YaHei", 12)
        font.setStyleStrategy(QFont.PreferAntialias)
        self.text_browser.setFont(font)

        # 垂直滚动到最新
        self.text_browser.verticalScrollBar().rangeChanged.connect(
            lambda: self.text_browser.moveCursor(QTextCursor.End)
        )

        layout.addWidget(self.text_browser)

    def append_text(self, text: str, color: str = None, bold: bool = False):
        """
        追加文本到日志

        Args:
            text: 文本内容
            color: 颜色名称（可选）
            bold: 是否加粗
        """
        self.text_browser.moveCursor(QTextCursor.End)
        char_format = self.text_browser.currentCharFormat()

        # 设置颜色
        if color and color in COLOR_MAP:
            char_format.setForeground(COLOR_MAP[color])
        else:
            char_format.setForeground(COLOR_MAP["white"])

        # 设置粗体
        font = char_format.font()
        font.setBold(bold)
        font.setPointSize(12)
        char_format.setFont(font)

        # 插入文本
        cursor = self.text_browser.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text + "\n", char_format)

        # 记录历史
        self._text_history.append(text)

        # 自动滚动到底部
        self.text_browser.moveCursor(QTextCursor.End)

    def clear_text(self):
        """清空所有文本"""
        self.text_browser.clear()
        self._text_history.clear()

    def get_history(self) -> list[str]:
        """获取文本历史"""
        return self._text_history.copy()

    # ==================== 事件总线接口 ====================

    def on_text_display(self, text: str, color: str = None, bold: bool = False, **kwargs):
        """事件总线回调：显示文本"""
        self.append_text(text, color, bold)

    def on_clear(self, **kwargs):
        """事件总线回调：清空文本"""
        self.clear_text()
