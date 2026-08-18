"""
游戏状态栏组件 (status_bar.py)

顶部固定状态栏，两行布局：
  第1行 — 世界状态: 天数(曜日) | 时段 | 天气 | 所持金
  第2行 — 玩家状态: HP条 | MP条（可扩展更多属性）

终端风格：暗底亮字，Consolas 11pt，Unicode 块字符进度条。
事件驱动刷新：监听事件总线，拉取 GameContext 全量更新。
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
import logging

logger = logging.getLogger(__name__)

# ─── 星期映射（day 1 = 月曜日） ───
_WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

# ─── 时段显示名 ───
_TIME_LABELS = {
    "morning":   "朝",
    "afternoon": "昼",
    "evening":   "夕",
    "night":     "夜",
    "dawn":      "暁",
}

# ─── 天气显示名 ───
_WEATHER_LABELS = {
    "clear":  "晴",
    "cloudy": "曇",
    "rain":   "雨",
    "snow":   "雪",
}

# ─── 进度条常量 ───
BAR_BLOCKS = 10          # 总块数
BLOCK_FILLED = "▅"       # U+2585
BLOCK_EMPTY  = "░"       # U+2591


def _weekday(day: int) -> str:
    """day 从 1 开始，1 = 月曜日"""
    return _WEEKDAYS[(day - 1) % 7]


def _time_label(time_str: str) -> str:
    return _TIME_LABELS.get(time_str, time_str)


def _weather_label(weather_str: str) -> str:
    return _WEATHER_LABELS.get(weather_str, weather_str)


def _bar_html(current: int, maximum: int) -> str:
    """
    生成进度条的 HTML 字符串。

    10 块，颜色三段：
      > 50%  → 绿色  #60FF60
      20-50% → 黄色  #FFFF60
      < 20%  → 红色  #FF6060
    空块 → 暗灰 #303030
    """
    if maximum <= 0:
        maximum = 1
    ratio = max(0.0, min(1.0, current / maximum))
    filled = round(ratio * BAR_BLOCKS)
    empty = BAR_BLOCKS - filled

    if ratio > 0.5:
        color = "#60FF60"
    elif ratio >= 0.2:
        color = "#FFFF60"
    else:
        color = "#FF6060"

    html = f'<span style="color:{color};">{BLOCK_FILLED * filled}</span>'
    html += f'<span style="color:#303030;">{BLOCK_EMPTY * empty}</span>'
    return html


class GameStatusBar(QWidget):
    """
    顶部游戏状态栏

    两行布局，终端风格。通过事件总线接收变化通知，
    从 GameContext 拉取最新数据全量刷新。

    使用示例：
        status_bar = GameStatusBar(event_bus, game_context)
        layout.addWidget(status_bar)
    """

    def __init__(self, event_bus=None, game_context=None, parent=None):
        super().__init__(parent)
        self._event_bus = event_bus
        self._context = game_context
        self._connections: list = []

        self._setup_ui()
        self._connect_events()

        logger.info("GameStatusBar 初始化完成")

    def _setup_ui(self):
        """构建两行布局"""
        self.setFixedHeight(52)
        self.setStyleSheet("""
            GameStatusBar {
                background-color: #141414;
                border-bottom: 1px solid #252525;
            }
        """)

        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.Monospace)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 4, 16, 4)
        root.setSpacing(2)

        # ── 第 1 行：世界状态 ──
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(0)

        self._day_label = QLabel("Day 1 (月)")
        self._day_label.setFont(font)
        self._day_label.setStyleSheet("color: #D0D0D0;")

        self._time_label = QLabel("朝")
        self._time_label.setFont(font)
        self._time_label.setStyleSheet("color: #60FFFF;")

        self._weather_label = QLabel("晴")
        self._weather_label.setFont(font)
        self._weather_label.setStyleSheet("color: #FFFF60;")

        self._money_label = QLabel("所持金: 0")
        self._money_label.setFont(font)
        self._money_label.setStyleSheet("color: #FFD700;")

        # 分隔符
        sep1 = QLabel("│")
        sep1.setFont(font)
        sep1.setStyleSheet("color: #303030;")
        sep2 = QLabel("│")
        sep2.setFont(font)
        sep2.setStyleSheet("color: #303030;")
        sep3 = QLabel("│")
        sep3.setFont(font)
        sep3.setStyleSheet("color: #303030;")

        row1.addWidget(self._day_label)
        row1.addWidget(sep1)
        row1.addWidget(self._time_label)
        row1.addWidget(sep2)
        row1.addWidget(self._weather_label)
        row1.addWidget(sep3)
        row1.addWidget(self._money_label)
        row1.addStretch()

        root.addLayout(row1)

        # ── 第 2 行：玩家状态 ──
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(24)

        self._hp_label = QLabel("HP ░░░░░░░░░░ (0/100)")
        self._hp_label.setFont(font)
        self._hp_label.setTextFormat(Qt.RichText)

        self._mp_label = QLabel("MP ░░░░░░░░░░ (0/50)")
        self._mp_label.setFont(font)
        self._mp_label.setTextFormat(Qt.RichText)

        # 标签前缀
        hp_prefix = QLabel("HP")
        hp_prefix.setFont(font)
        hp_prefix.setStyleSheet("color: #FF6060;")
        mp_prefix = QLabel("MP")
        mp_prefix.setFont(font)
        mp_prefix.setStyleSheet("color: #60A0FF;")

        hp_group = QHBoxLayout()
        hp_group.setSpacing(4)
        hp_group.addWidget(hp_prefix)
        hp_group.addWidget(self._hp_label)

        mp_group = QHBoxLayout()
        mp_group.setSpacing(4)
        mp_group.addWidget(mp_prefix)
        mp_group.addWidget(self._mp_label)

        row2.addLayout(hp_group)
        row2.addLayout(mp_group)
        row2.addStretch()

        root.addLayout(row2)

    def _connect_events(self):
        """订阅事件总线，变化时全量刷新"""
        if not self._event_bus:
            return

        bus = self._event_bus
        # 用命名函数而非 lambda，确保可以正确退订
        def on_refresh(**kw):
            self.refresh()

        events = [
            "on_game_start",
            "on_day_begin",
            "on_time_change",
            "on_location_change",
            "character_stat_changed",
        ]
        for event_name in events:
            bus.subscribe(event_name, on_refresh)
            self._connections.append((event_name, on_refresh))

    # ─── 公开接口 ───────────────────────────────────────

    def refresh(self):
        """从 GameContext 拉取最新数据并刷新显示"""
        if not self._context:
            return

        ctx = self._context

        # ── 第 1 行 ──
        day = ctx.get_day()
        self._day_label.setText(f"Day {day} ({_weekday(day)})")

        time_str = ctx.get_time_of_day().value if hasattr(ctx.get_time_of_day(), 'value') else str(ctx.get_time_of_day())
        self._time_label.setText(_time_label(time_str))

        weather = ctx.get_world("weather", "clear")
        self._weather_label.setText(_weather_label(weather))

        money = ctx.get_player_stat("money", 0)
        self._money_label.setText(f"所持金: {money:,}")

        # ── 第 2 行 ──
        hp = ctx.get_player_stat("hp", 0)
        max_hp = ctx.get_player_stat("max_hp", 100)
        self._hp_label.setText(
            f'{_bar_html(hp, max_hp)} <span style="color:#D0D0D0;">({hp}/{max_hp})</span>'
        )

        mp = ctx.get_player_stat("mp", 0)
        max_mp = ctx.get_player_stat("max_mp", 50)
        self._mp_label.setText(
            f'{_bar_html(mp, max_mp)} <span style="color:#D0D0D0;">({mp}/{max_mp})</span>'
        )

    def cleanup(self):
        """取消所有事件订阅"""
        if self._event_bus:
            bus = self._event_bus
            for event_name, callback in self._connections:
                try:
                    bus.unsubscribe(event_name, callback)
                except Exception as e:
                    logger.warning(f"移除事件连接失败 {event_name}: {e}")
        self._connections.clear()
