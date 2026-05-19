"""
控制台文本组件 (console_widget.py)

命令行风格的纯文本界面组件。
统一处理文本显示和选项输入，替代 LogWidget + ChoiceWidget。

特性：
- 终端风格（暗底亮字，等宽字体）
- 文本颜色/粗体支持
- 选项嵌入文本流（数字快捷键 + 回车确认）
- 键盘输入（按数字键选选项）
- ASCII 艺术字符画

事件总线接口：
  接收: ui.text_display / ui.clear / ui.choice_show / ui.input_show
  发射: ui.choice_made
"""

from PySide6.QtWidgets import QTextEdit, QWidget, QVBoxLayout
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import (
    QFont, QTextCursor, QColor, QTextCharFormat,
    QKeyEvent, QMouseEvent
)
import logging

logger = logging.getLogger(__name__)

# 终端配色方案
CLR = {
    "white":   QColor("#D0D0D0"),
    "red":     QColor("#FF6060"),
    "green":   QColor("#60FF60"),
    "blue":    QColor("#60A0FF"),
    "yellow":  QColor("#FFFF60"),
    "cyan":    QColor("#60FFFF"),
    "magenta": QColor("#FF60FF"),
    "pink":    QColor("#FFA0D0"),
    "gray":    QColor("#707070"),
    "black":   QColor("#000000"),
    "bg":      QColor("#0C0C0C"),
    "dim":     QColor("#505050"),
    "menu":    QColor("#E0C060"),   # 菜单项金色
    "accent":  QColor("#FF8040"),   # 高亮强调色
}


class ConsoleWidget(QWidget):
    """
    终端风格主控制台

    既是文本日志，也是输入界面。选项以行内编号方式显示，
    玩家按数字键或点击即选择。
    """

    # 信号：玩家选择了某个选项
    choice_made = Signal(int)

    def __init__(self, event_bus=None, parent=None):
        super().__init__(parent)
        self._event_bus = event_bus

        self._setup_ui()

        # 等待状态
        self._waiting_choice = False
        self._choice_options: list[str] = []
        self._waiting_input = False

        logger.info("ConsoleWidget 初始化完成 (终端模式)")

    def _setup_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._editor = QTextEdit(self)
        self._editor.setReadOnly(True)
        self._editor.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._editor.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._editor.setLineWrapMode(QTextEdit.WidgetWidth)

        # 终端字体
        font = QFont("Consolas", 13)
        font.setStyleHint(QFont.Monospace)
        self._editor.setFont(font)

        # 终端配色
        self._editor.setStyleSheet(f"""
            QTextEdit {{
                background-color: {CLR['bg'].name()};
                color: {CLR['white'].name()};
                border: none;
                padding: 20px 24px;
                selection-background-color: #303030;
            }}
            QScrollBar:vertical {{
                width: 8px;
                background: {CLR['bg'].name()};
            }}
            QScrollBar::handle:vertical {{
                background: #303030;
                border-radius: 4px;
                min-height: 24px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        # 光标保持文本颜色
        self._editor.setCursorWidth(0)  # 隐藏闪烁光标（只读模式）

        layout.addWidget(self._editor)

    # ─── 公开 API ─────────────────────────────────────

    def write(self, text: str, color: str = "white", bold: bool = False):
        """追加一行文本"""
        fmt = self._make_format(color, bold)
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text + "\n", fmt)
        self._scroll_to_end()

    def write_center(self, text: str, color: str = "white", bold: bool = False):
        """追加居中文本（用空格填充）"""
        self.write(text, color, bold)  # 简化：左对齐

    def write_blank(self):
        """追加空行"""
        self.write("")

    def clear(self):
        """清空控制台"""
        self._editor.clear()

    def show_choices(self, options: list[str]) -> int:
        """嵌入选项文本并等待选择（同步阻塞，由 QEventLoop 驱动）"""
        self._choice_options = options
        self._waiting_choice = True

        # 写入选项
        self.write("")  # 空行
        for i, opt in enumerate(options, 1):
            self.write(f"  [{i}]  {opt}", "menu", False)
        self.write("")
        self.write("  ▸ 按数字键选择...", "dim")

        # 注意：不在这里 wait，由 api_bridge 的 scheduler.wait_for_choice() 负责

    def hide_choices(self):
        """清除等待状态"""
        self._waiting_choice = False
        self._choice_options.clear()

    def start_waiting(self, option_count: int):
        """进入等待状态（不写入任何文本，只激活数字键监听）

        Args:
            option_count: 选项数量（用于范围校验，超出范围映射到最后一个）
        """
        self._waiting_choice = True
        self._choice_options = [f"选项{i}" for i in range(1, option_count + 1)]

    def stop_waiting(self):
        """退出等待状态"""
        self._waiting_choice = False
        self._choice_options.clear()

    def get_choice_result(self) -> int:
        """获取最近的选项结果（-1 表示未选择）"""
        return self._last_choice if hasattr(self, '_last_choice') else -1

    # ─── 键盘事件 ────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent):
        """拦截键盘事件"""
        if self._waiting_choice:
            # 数字键 1-9
            key = event.key()
            if Qt.Key_1 <= key <= Qt.Key_9:
                idx = key - Qt.Key_0  # 1-based
                if 1 <= idx <= len(self._choice_options):
                    self._resolve_choice(idx)
                    return
            elif key in (Qt.Key_Return, Qt.Key_Enter):
                # 回车默认选 1
                if len(self._choice_options) > 0:
                    self._resolve_choice(1)
                    return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """双击选择"""
        if self._waiting_choice:
            # 获取点击位置的行号...
            cursor = self._editor.cursorForPosition(event.pos())
            line_text = cursor.block().text()
            # 简单解析 [1] 格式
            import re
            m = re.match(r'\s*\[(\d+)\]', line_text)
            if m:
                idx = int(m.group(1))
                if 1 <= idx <= len(self._choice_options):
                    self._resolve_choice(idx)
                    return
        super().mouseDoubleClickEvent(event)

    def _resolve_choice(self, index: int):
        """玩家做出了选择"""
        logger.info(f"控制台选择: {index}")
        self._last_choice = index
        self._waiting_choice = False

        # 回显选择
        self.write(f"  > {self._choice_options[index - 1]}", "accent", True)
        self.write("")

        self.choice_made.emit(index)

        # 发射事件总线事件
        if self._event_bus:
            self._event_bus.emit("ui.choice_made", choice_index=index)

    # ─── 内部工具 ────────────────────────────────────

    def _make_format(self, color: str, bold: bool) -> QTextCharFormat:
        """构建文本格式"""
        fmt = QTextCharFormat()
        fmt.setForeground(CLR.get(color, CLR["white"]))
        f = self._editor.font()
        f.setBold(bold)
        fmt.setFont(f)
        return fmt

    def _scroll_to_end(self):
        """滚动到底部"""
        sb = self._editor.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ─── 事件总线回调 ────────────────────────────────

    def on_text_display(self, text: str, color: str = None, bold: bool = False, **kwargs):
        self.write(text, color or "white", bold)

    def on_clear(self, **kwargs):
        self.clear()

    def on_choice_show(self, options: list, **kwargs):
        self.show_choices(list(options))
