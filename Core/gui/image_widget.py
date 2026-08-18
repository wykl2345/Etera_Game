"""
图片/立绘显示组件 (image_widget.py)

负责显示背景图、角色立绘、物品图标等视觉元素。
通过事件总线接收 ui.image_show/hide, ui.character_show/hide 等事件。

支持：
- 背景图切换（淡入淡出）
- 角色立绘显示（左右中三位置）
- 图片渐入渐出效果
"""

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class FadeLabel(QLabel):
    """支持淡入淡出的图片标签"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(500)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.setAlignment(Qt.AlignCenter)
        self.hide()

    def fade_in(self, pixmap: QPixmap = None):
        """淡入显示"""
        if pixmap:
            self.setPixmap(pixmap)
        self.setWindowOpacity(0.0)
        self.show()
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.start()

    def fade_out(self, on_finished=None):
        """淡出隐藏"""
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        if on_finished:
            self._fade_anim.finished.connect(lambda: (self.hide(), on_finished()))
        else:
            self._fade_anim.finished.connect(self.hide)
        self._fade_anim.start()


class ImageWidget(QWidget):
    """图片/立绘显示组件"""

    # 位置常量
    POSITION_LEFT = "left"
    POSITION_CENTER = "center"
    POSITION_RIGHT = "right"

    def __init__(self, resource_base: Path = None, resource_manager=None, parent=None):
        super().__init__(parent)
        self._resource_base = resource_base or Path("resources/images")
        self._resource_manager = resource_manager

        self._setup_ui()
        self._image_labels: dict[str, FadeLabel] = {}
        self._character_labels: dict[str, FadeLabel] = {}

        logger.info("ImageWidget 初始化完成")

    def _setup_ui(self):
        """初始化UI"""
        # 使用水平布局排布三个位置
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # 左侧位置（角色立绘）
        self._left_area = QWidget()
        left_layout = QVBoxLayout(self._left_area)
        left_layout.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        left_layout.setContentsMargins(20, 0, 0, 20)
        self._layout.addWidget(self._left_area, 1)

        # 中央位置（背景或主要图片）
        self._center_area = QWidget()
        center_layout = QVBoxLayout(self._center_area)
        center_layout.setAlignment(Qt.AlignCenter)
        center_layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self._center_area, 2)

        # 右侧位置（角色立绘）
        self._right_area = QWidget()
        right_layout = QVBoxLayout(self._right_area)
        right_layout.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        right_layout.setContentsMargins(0, 0, 20, 20)
        self._layout.addWidget(self._right_area, 1)

        # 存储区域引用
        self._position_areas = {
            self.POSITION_LEFT: self._left_area,
            self.POSITION_CENTER: self._center_area,
            self.POSITION_RIGHT: self._right_area,
        }

    def _get_position_area(self, position: str) -> QWidget:
        """获取指定位置的容器"""
        return self._position_areas.get(position, self._center_area)

    def _load_pixmap(self, name: str, target_w: int = 400, target_h: int = 600) -> QPixmap | None:
        """
        加载图片资源（委托给 ResourceManager）

        如果 ResourceManager 可用，通过其统一接口加载（含缓存）；
        否则回退到直接文件加载。

        Args:
            name: 图片名称（不含路径和后缀）
            target_w: 目标宽度
            target_h: 目标高度

        Returns:
            QPixmap | None: 加载成功的图片
        """
        if self._resource_manager:
            return self._resource_manager.load_image(name, target_width=target_w, target_height=target_h)

        # 回退：直接文件加载
        extensions = [".png", ".jpg", ".jpeg", ".webp", ".gif"]
        for ext in extensions:
            path = self._resource_base / f"{name}{ext}"
            if path.exists():
                pixmap = QPixmap(str(path))
                if not pixmap.isNull():
                    pixmap = pixmap.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    return pixmap

        logger.warning(f"图片资源未找到: {name}")
        return None

    def show_image(self, name: str, position: str = "center", fade: bool = True):
        """
        显示图片

        Args:
            name: 图片资源名称
            position: 显示位置 (left/center/right)
            fade: 是否使用淡入效果
        """
        pixmap = self._load_pixmap(name)
        if not pixmap:
            # 显示占位文字
            self._show_placeholder(name, position)
            return

        # 移除旧图片
        if name in self._image_labels:
            old_label = self._image_labels.pop(name)
            old_label.deleteLater()

        label = FadeLabel()
        self._image_labels[name] = label

        # 添加到对应位置
        area = self._get_position_area(position)
        area.layout().addWidget(label)

        if fade:
            label.fade_in(pixmap)
        else:
            label.setPixmap(pixmap)
            label.show()

        logger.info(f"图片显示: {name} @ {position}")

    def hide_image(self, name: str, fade: bool = True):
        """
        隐藏图片

        Args:
            name: 图片资源名称
            fade: 是否使用淡出效果
        """
        if name not in self._image_labels:
            return

        label = self._image_labels.pop(name)
        if fade:
            label.fade_out(on_finished=label.deleteLater)
        else:
            label.hide()
            label.deleteLater()

        logger.info(f"图片隐藏: {name}")

    def show_character(self, char_id: str, expression: str = "normal", position: str = "center"):
        """
        显示角色立绘

        Args:
            char_id: 角色ID
            expression: 表情/状态
            position: 显示位置
        """
        # 构建立绘资源名
        image_name = f"{char_id}_{expression}"
        pixmap = self._load_pixmap(image_name)

        if not pixmap:
            # 尝试加载角色基础立绘
            pixmap = self._load_pixmap(char_id)

        if not pixmap:
            # 显示角色名占位
            self._show_character_placeholder(char_id, position)
            return

        # 移除旧立绘
        if char_id in self._character_labels:
            old_label = self._character_labels.pop(char_id)
            old_label.fade_out(on_finished=old_label.deleteLater)

        label = FadeLabel()
        self._character_labels[char_id] = label

        # 角色立绘用更大的目标尺寸加载
        if self._resource_manager:
            char_pixmap = self._resource_manager.load_image(
                image_name, target_width=300, target_height=500
            )
            if not char_pixmap:
                char_pixmap = self._resource_manager.load_image(
                    char_id, target_width=300, target_height=500
                )
        else:
            char_pixmap = pixmap.scaled(
                300, 500,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        label.setPixmap(char_pixmap or pixmap)

        area = self._get_position_area(position)
        area.layout().addWidget(label)
        label.fade_in()

        logger.info(f"角色立绘显示: {char_id}({expression}) @ {position}")

    def hide_character(self, char_id: str):
        """
        隐藏角色立绘

        Args:
            char_id: 角色ID
        """
        if char_id not in self._character_labels:
            return

        label = self._character_labels.pop(char_id)
        label.fade_out(on_finished=label.deleteLater)
        logger.info(f"角色立绘隐藏: {char_id}")

    def set_background(self, name: str, transition: str = "fade"):
        """
        设置背景

        Args:
            name: 背景图片名称
            transition: 过渡效果 (fade/slide/none)
        """
        # 清除所有处于 center 位置的图片（背景）
        labels_to_remove = [
            k for k, v in self._image_labels.items()
            if v.parent() == self._center_area
        ]
        for key in labels_to_remove:
            label = self._image_labels.pop(key)
            label.fade_out(on_finished=label.deleteLater)

        # 显示新背景
        self.show_image(f"bg_{name}", "center", transition == "fade")
        logger.info(f"背景设置: {name} ({transition})")

    def _show_placeholder(self, name: str, position: str):
        """显示图片占位文字"""
        label = QLabel(f"[ {name} ]")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #555; font-size: 18px; padding: 40px;")
        area = self._get_position_area(position)
        area.layout().addWidget(label)
        self._image_labels[name] = FadeLabel()  # 占位，防止重复加载

    def _show_character_placeholder(self, char_id: str, position: str):
        """显示角色立绘占位"""
        label = QLabel(f"[ {char_id} ]")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #888; font-size: 24px; padding: 60px;")
        area = self._get_position_area(position)
        area.layout().addWidget(label)

    def clear_all(self):
        """清除所有图片和立绘"""
        for label in list(self._image_labels.values()):
            label.hide()
            label.deleteLater()
        self._image_labels.clear()

        for label in list(self._character_labels.values()):
            label.hide()
            label.deleteLater()
        self._character_labels.clear()

        logger.info("所有图片已清除")

    # ==================== 事件总线接口 ====================

    def on_image_show(self, name: str, position: str = "center", fade: bool = True, **kwargs):
        self.show_image(name, position, fade)

    def on_image_hide(self, name: str, fade: bool = True, **kwargs):
        self.hide_image(name, fade)

    def on_character_show(self, char_id: str, expression: str = "normal", position: str = "center", **kwargs):
        self.show_character(char_id, expression, position)

    def on_character_hide(self, char_id: str, **kwargs):
        self.hide_character(char_id)

    def on_background_set(self, name: str, transition: str = "fade", **kwargs):
        self.set_background(name, transition)
