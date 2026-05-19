"""
API桥接模块 (api_bridge.py)

本模块是Lua脚本与Python引擎之间的安全边界，采用白名单机制。
只有在本模块中显式暴露的函数才能被Lua脚本调用，
任何文件系统、网络操作都无法触及。

暴露给脚本的API分组：
- UI类：文本显示、图片展示、声音播放、用户输入
- 数据读写类：角色数据、物品数据、Flag读写
- 事件类：事件触发、延迟执行
- 工具类：随机数、日志输出

设计要点：
- 使用装饰器进行API注册
- 严格限制参数类型和返回值
- 记录所有API调用日志
- 提供完整的错误处理
"""

import random
import logging
from typing import Any, Dict, List, Optional, Callable, Union
from dataclasses import dataclass
from enum import Enum


# 配置日志记录器
logger = logging.getLogger(__name__)


class TextColor(Enum):
    """文本颜色枚举"""
    WHITE = "white"
    RED = "red"
    GREEN = "green"
    BLUE = "blue"
    YELLOW = "yellow"
    CYAN = "cyan"
    MAGENTA = "magenta"
    PINK = "pink"
    GRAY = "gray"
    BLACK = "black"


@dataclass
class ChoiceOption:
    """选择项配置"""
    text: str
    value: int
    requires: Optional[Callable[[], bool]] = None  # 显示条件


class LuaAPI:
    """
    Lua API桥接器

    提供Lua脚本可以调用的所有函数。这是安全边界的核心，
    所有暴露给脚本的API都必须在这里注册。

    使用示例：
        # 在引擎初始化时
        api = LuaAPI(scheduler, context, event_bus)
        env = api.build_env()

        # 在Lua脚本中可以这样调用：
        -- ui.text("你好")
        -- local choice = ui.ask_choice({"选项1", "选项2"})
        -- data.set_flag("story", "completed", true)
    """

    def __init__(
        self,
        scheduler: Any,
        context: Any,
        event_bus: Any,
        resource_manager: Any = None
    ):
        """
        初始化API桥接器

        Args:
            scheduler: 脚本调度器实例
            context: 游戏上下文实例
            event_bus: 事件总线实例
            resource_manager: 资源管理器实例（可选）
        """
        self.scheduler = scheduler
        self.context = context
        self.event_bus = event_bus
        self.resource_manager = resource_manager

        # 调试模式标志
        self.debug_mode: bool = False

        logger.info("API桥接器初始化完成")

    def build_env(self) -> Dict[str, Any]:
        """
        构建注入到Lua环境的全局函数表

        Returns:
            Dict[str, Any]: 函数名字典，可直接合并到Lua globals
        """
        return {
            # UI类API
            "ui": self._build_ui_api(),

            # 数据读写类API
            "data": self._build_data_api(),

            # 事件类API
            "event": self._build_event_api(),

            # 工具类API
            "util": self._build_util_api(),

            # 世界状态API
            "world": self._build_world_api(),
        }

    def _build_ui_api(self) -> Dict[str, Any]:
        """构建UI类API"""
        return {
            "text": self._ui_text,
            "clear": self._ui_clear,
            "show_image": self._ui_show_image,
            "hide_image": self._ui_hide_image,
            "play_sound": self._ui_play_sound,
            "stop_sound": self._ui_stop_sound,
            "play_music": self._ui_play_music,
            "stop_music": self._ui_stop_music,
            "ask_choice": self._ui_ask_choice,
            "ask_input": self._ui_ask_input,
            "set_background": self._ui_set_background,
            "show_character": self._ui_show_character,
            "hide_character": self._ui_hide_character,
        }

    def _build_data_api(self) -> Dict[str, Any]:
        """构建数据读写类API"""
        return {
            "get_chara": self._data_get_chara,
            "set_stat": self._data_set_stat,
            "get_stat": self._data_get_stat,
            "get_relation": self._data_get_relation,
            "set_relation": self._data_set_relation,
            "modify_relation": self._data_modify_relation,
            "get_flag": self._data_get_flag,
            "set_flag": self._data_set_flag,
            "has_flag": self._data_has_flag,
            "get_inventory": self._data_get_inventory,
            "add_item": self._data_add_item,
            "remove_item": self._data_remove_item,
            "get_item_count": self._data_get_item_count,
        }

    def _build_event_api(self) -> Dict[str, Any]:
        """构建事件类API"""
        return {
            "emit": self._event_emit,
            "after_days": self._event_after_days,
            "listen": self._event_listen,
        }

    def _build_util_api(self) -> Dict[str, Any]:
        """构建工具类API"""
        return {
            "random": self._util_random,
            "random_range": self._util_random_range,
            "log": self._util_log,
            "debug": self._util_debug,
            "sleep": self._util_sleep,
        }

    def _build_world_api(self) -> Dict[str, Any]:
        """构建世界状态API"""
        return {
            "get_day": self._world_get_day,
            "set_day": self._world_set_day,
            "get_time": self._world_get_time,
            "set_time": self._world_set_time,
            "get_location": self._world_get_location,
            "set_location": self._world_set_location,
        }

    # ==================== UI类实现 ====================

    def _ui_text(
        self,
        text: str,
        color: Optional[str] = None,
        bold: bool = False
    ) -> None:
        """
        显示文本

        Args:
            text: 要显示的文本内容
            color: 文本颜色（可选）
            bold: 是否加粗（可选）
        """
        if not isinstance(text, str):
            logger.error(f"ui.text: text must be string, got {type(text)}")
            return

        # 验证颜色值
        if color and color not in [c.value for c in TextColor]:
            logger.warning(f"ui.text: unknown color '{color}', ignoring")
            color = None

        # 发送显示文本事件
        self.event_bus.emit("ui.text_display", text=text, color=color, bold=bold)
        logger.debug(f"UI: text displayed - {text[:50]}...")

    def _ui_clear(self) -> None:
        """清空文本显示区域"""
        self.event_bus.emit("ui.clear")
        logger.debug("UI: display cleared")

    def _ui_show_image(
        self,
        name: str,
        position: str = "center",
        fade: bool = True
    ) -> None:
        """
        显示图片

        Args:
            name: 图片资源名称
            position: 显示位置 (left/center/right/custom)
            fade: 是否使用淡入效果
        """
        if not isinstance(name, str):
            logger.error(f"ui.show_image: name must be string")
            return

        self.event_bus.emit(
            "ui.image_show",
            name=name,
            position=position,
            fade=fade
        )
        logger.debug(f"UI: image shown - {name} at {position}")

    def _ui_hide_image(self, name: str, fade: bool = True) -> None:
        """
        隐藏图片

        Args:
            name: 图片资源名称
            fade: 是否使用淡出效果
        """
        self.event_bus.emit("ui.image_hide", name=name, fade=fade)
        logger.debug(f"UI: image hidden - {name}")

    def _ui_play_sound(self, name: str, volume: float = 1.0) -> None:
        """
        播放音效

        Args:
            name: 音效资源名称
            volume: 音量 (0.0 - 1.0)
        """
        volume = max(0.0, min(1.0, volume))
        self.event_bus.emit("audio.sound_play", name=name, volume=volume)
        logger.debug(f"UI: sound played - {name}")

    def _ui_stop_sound(self, name: str) -> None:
        """停止播放音效"""
        self.event_bus.emit("audio.sound_stop", name=name)

    def _ui_play_music(self, name: str, volume: float = 0.8, loop: bool = True) -> None:
        """
        播放背景音乐

        Args:
            name: 音乐资源名称
            volume: 音量 (0.0 - 1.0)
            loop: 是否循环播放
        """
        volume = max(0.0, min(1.0, volume))
        self.event_bus.emit(
            "audio.music_play",
            name=name,
            volume=volume,
            loop=loop
        )
        logger.debug(f"UI: music played - {name}")

    def _ui_stop_music(self, fade_out: bool = True) -> None:
        """停止播放背景音乐"""
        self.event_bus.emit("audio.music_stop", fade_out=fade_out)

    def _ui_ask_choice(self, options: List[str]) -> int:
        """
        显示选择菜单并等待玩家选择

        这是一个阻塞调用，会暂停脚本执行直到玩家做出选择。

        Args:
            options: 选择项列表

        Returns:
            int: 玩家选择的索引（从1开始）
        """
        if not isinstance(options, list) or len(options) == 0:
            logger.error("ui.ask_choice: options must be non-empty list")
            return 0

        # 发送选择菜单显示事件
        self.event_bus.emit(
            "ui.choice_show",
            options=options
        )

        # 等待玩家输入
        result = self.scheduler.wait_for_choice()

        logger.debug(f"UI: choice made - option {result}")
        return result

    def _ui_ask_input(self, prompt: str, default: str = "", max_length: int = 100) -> str:
        """
        显示输入框并等待玩家输入

        Args:
            prompt: 输入提示文本
            default: 默认值
            max_length: 最大输入长度

        Returns:
            str: 玩家输入的文本
        """
        if not isinstance(prompt, str):
            prompt = str(prompt)

        self.event_bus.emit(
            "ui.input_show",
            prompt=prompt,
            default=default,
            max_length=max_length
        )

        result = self.scheduler.wait_for_input()
        logger.debug(f"UI: input received - {result[:20]}...")
        return result

    def _ui_set_background(self, name: str, transition: str = "fade") -> None:
        """
        设置背景

        Args:
            name: 背景图片名称
            transition: 过渡效果 (fade/slide/none)
        """
        self.event_bus.emit(
            "ui.background_set",
            name=name,
            transition=transition
        )

    def _ui_show_character(
        self,
        char_id: str,
        expression: str = "normal",
        position: str = "center"
    ) -> None:
        """
        显示角色立绘

        Args:
            char_id: 角色ID
            expression: 表情/状态
            position: 显示位置
        """
        self.event_bus.emit(
            "ui.character_show",
            char_id=char_id,
            expression=expression,
            position=position
        )

    def _ui_hide_character(self, char_id: str) -> None:
        """隐藏角色立绘"""
        self.event_bus.emit("ui.character_hide", char_id=char_id)

    # ==================== 数据读写类实现 ====================

    def _data_get_chara(self, char_id: str) -> Optional[Dict[str, Any]]:
        """
        获取角色数据

        Args:
            char_id: 角色ID

        Returns:
            Optional[Dict]: 角色数据字典，如果角色不存在返回None
        """
        char = self.context.get_character(char_id)
        if char:
            return {
                "id": char.id,
                "name": char.name,
                "stats": char.stats.to_dict(),
                "relation": char.relation,
                "location": char.location,
            }
        logger.warning(f"data.get_chara: character not found - {char_id}")
        return None

    def _data_set_stat(
        self,
        target: str,
        stat_name: str,
        value: Union[int, float]
    ) -> bool:
        """
        设置属性值

        Args:
            target: 目标类型 ("player" 或角色ID)
            stat_name: 属性名称
            value: 属性值

        Returns:
            bool: 是否设置成功
        """
        try:
            # relation 不是 StatBlock 属性，转发到专门的 relation 方法
            if stat_name == "relation":
                if target == "player":
                    logger.warning("player has no relation stat")
                    return False
                self.context.set_character_relation(target, int(value))
                self.event_bus.emit(
                    "character_relation_changed",
                    target=target,
                    value=value
                )
                return True

            if target == "player":
                self.context.set_player_stat(stat_name, int(value))
                self.event_bus.emit(
                    "character_stat_changed",
                    target="player",
                    stat=stat_name,
                    value=value
                )
                return True
            else:
                self.context.set_character_stat(target, stat_name, int(value))
                self.event_bus.emit(
                    "character_stat_changed",
                    target=target,
                    stat=stat_name,
                    value=value
                )
                return True
        except Exception as e:
            logger.error(f"data.set_stat failed: {e}")
            return False

    def _data_get_stat(self, target: str, stat_name: str, default: int = 0) -> int:
        """
        获取属性值

        Args:
            target: 目标类型 ("player" 或角色ID)
            stat_name: 属性名称
            default: 默认值

        Returns:
            int: 属性值
        """
        if target == "player":
            return self.context.get_player_stat(stat_name, default)
        else:
            return self.context.get_character_stat(target, stat_name, default)

    def _data_get_flag(
        self,
        namespace: str,
        key: str,
        default: Any = None
    ) -> Any:
        """
        获取Flag值

        Args:
            namespace: 命名空间
            key: Flag键
            default: 默认值

        Returns:
            Any: Flag值
        """
        # 角色Flag的特殊处理
        if namespace.startswith("char:"):
            char_id = namespace[5:]
            return self.context.get_character_flag(char_id, key, default)

        return self.context.get_global_flag(namespace, key, default)

    def _data_set_flag(
        self,
        namespace: str,
        key: str,
        value: Any
    ) -> bool:
        """
        设置Flag值

        Args:
            namespace: 命名空间
            key: Flag键
            value: Flag值

        Returns:
            bool: 是否设置成功
        """
        # 角色Flag的特殊处理
        if namespace.startswith("char:"):
            char_id = namespace[5:]
            self.context.set_character_flag(char_id, key, value)
            return True

        # 保护核心命名空间
        if namespace == "core":
            logger.warning("Cannot modify core namespace flags")
            return False

        self.context.set_global_flag(namespace, key, value)
        logger.debug(f"Flag set: [{namespace}] {key} = {value}")
        return True

    def _data_has_flag(self, namespace: str, key: str) -> bool:
        """检查Flag是否存在"""
        if namespace.startswith("char:"):
            char_id = namespace[5:]
            return self.context.get_character_flag(char_id, key) is not None
        return self.context.has_global_flag(namespace, key)

    def _data_get_inventory(self) -> Dict[str, int]:
        """获取背包物品列表"""
        return self.context.get_inventory().items

    def _data_add_item(self, item_id: str, count: int = 1) -> bool:
        """添加物品"""
        return self.context.add_item(item_id, count)

    def _data_remove_item(self, item_id: str, count: int = 1) -> bool:
        """移除物品"""
        return self.context.remove_item(item_id, count)

    def _data_get_relation(self, target: str) -> int:
        """
        获取好感度

        Args:
            target: 角色ID

        Returns:
            int: 好感度值
        """
        return self.context.get_character_relation(target)

    def _data_set_relation(self, target: str, value: int) -> bool:
        """
        设置好感度为绝对值

        Args:
            target: 角色ID
            value: 好感度值 (-100 ~ 100)

        Returns:
            bool: 是否成功
        """
        try:
            self.context.set_character_relation(target, int(value))
            self.event_bus.emit(
                "character_relation_changed",
                target=target,
                value=value
            )
            return True
        except Exception as e:
            logger.error(f"data.set_relation failed: {e}")
            return False

    def _data_modify_relation(self, target: str, delta: int) -> int:
        """
        增减好感度

        Args:
            target: 角色ID
            delta: 好感度变化量（正值增加，负值减少）

        Returns:
            int: 修改后的好感度值
        """
        new_value = self.context.modify_character_relation(target, int(delta))
        self.event_bus.emit(
            "character_relation_changed",
            target=target,
            value=new_value,
            delta=delta
        )
        return new_value

    def _data_get_item_count(self, item_id: str) -> int:
        """获取物品数量"""
        return self.context.get_item_count(item_id)

    # ==================== 事件类实现 ====================

    def _event_emit(self, event_name: str, payload: Optional[Dict] = None) -> None:
        """
        触发自定义事件

        Args:
            event_name: 事件名称
            payload: 事件数据（可选）
        """
        if not isinstance(event_name, str):
            logger.error("event.emit: event_name must be string")
            return

        data = payload or {}
        self.event_bus.emit(event_name, **data)
        logger.debug(f"Event emitted: {event_name}")

    def _event_after_days(self, days: int, callback: Callable) -> None:
        """
        安排days天后执行回调

        注意：这个函数在Lua沙箱中使用时，回调需要特殊处理。

        Args:
            days: 天数
            callback: 回调函数
        """
        if days < 1:
            logger.warning("event.after_days: days must be >= 1")
            return

        # 计算触发天数
        current_day = self.context.get_day()
        trigger_day = current_day + days

        # 设置一个Flag来标记延迟事件
        event_id = f"delayed_event_{random.randint(10000, 99999)}"
        self.context.set_temp(event_id, {
            "callback": callback,
            "trigger_day": trigger_day,
        })

        logger.debug(f"Event scheduled: {event_id} on day {trigger_day}")

    def _event_listen(self, event_name: str, handler: Callable) -> None:
        """
        监听事件

        Args:
            event_name: 事件名称
            handler: 处理函数
        """
        self.event_bus.subscribe(event_name, handler)
        logger.debug(f"Event listener added: {event_name}")

    # ==================== 工具类实现 ====================

    def _util_random(self) -> float:
        """获取0到1之间的随机浮点数"""
        return random.random()

    def _util_random_range(self, min_val: int, max_val: int) -> int:
        """
        获取指定范围内的随机整数

        Args:
            min_val: 最小值
            max_val: 最大值

        Returns:
            int: 随机整数
        """
        if min_val > max_val:
            min_val, max_val = max_val, min_val
        return random.randint(min_val, max_val)

    def _util_log(self, message: str) -> None:
        """
        输出日志（不影响游戏UI）

        Args:
            message: 日志消息
        """
        logger.info(f"[Lua] {message}")

    def _util_debug(self, message: str) -> None:
        """输出调试信息（仅调试模式）"""
        if self.debug_mode:
            logger.debug(f"[Lua] {message}")

    def _util_sleep(self, seconds: float) -> None:
        """
        暂停执行（毫秒级精度）

        Args:
            seconds: 暂停秒数
        """
        if seconds > 0:
            import time
            time.sleep(seconds)

    # ==================== 世界状态类实现 ====================

    def _world_get_day(self) -> int:
        """获取当前天数"""
        return self.context.get_day()

    def _world_set_day(self, day: int) -> None:
        """设置当前天数"""
        if day < 1:
            logger.warning("world.set_day: day must be >= 1")
            return
        self.context.set_day(day)

    def _world_get_time(self) -> str:
        """获取当前时段"""
        return self.context.get_time_of_day().value

    def _world_set_time(self, time: str) -> None:
        """设置当前时段"""
        self.context.set_time_of_day(time)

    def _world_get_location(self) -> str:
        """获取当前位置"""
        return self.context.get_location()

    def _world_set_location(self, location: str) -> None:
        """设置当前位置"""
        self.context.set_location(location)


class APIDocumentation:
    """
    API文档生成器

    用于生成Lua API的文档，方便Mod作者查阅。
    """

    @staticmethod
    def generate_markdown() -> str:
        """生成Markdown格式的API文档"""
        doc = """# Lua API 参考文档

## UI类 API

### ui.text(text, color?, bold?)
显示文本内容。

**参数：**
- `text` (string): 要显示的文本
- `color` (string, optional): 文本颜色
- `bold` (boolean, optional): 是否加粗

**示例：**
```lua
ui.text("你好，世界！")
ui.text("警告！", "red", true)
```

---

### ui.clear()
清空文本显示区域。

**示例：**
```lua
ui.clear()
```

---

### ui.show_image(name, position?, fade?)
显示图片。

**参数：**
- `name` (string): 图片资源名称
- `position` (string, optional): 显示位置 (left/center/right)
- `fade` (boolean, optional): 是否淡入

**示例：**
```lua
ui.show_image("background_castle")
ui.show_image("reimu_normal", "right", true)
```

---

### ui.play_sound(name, volume?)
播放音效。

**参数：**
- `name` (string): 音效资源名称
- `volume` (number, optional): 音量 (0.0-1.0)

---

### ui.ask_choice(options)
显示选择菜单并等待玩家选择。

**参数：**
- `options` (table): 选择项列表

**返回：**
- `number`: 玩家选择的索引（从1开始）

**示例：**
```lua
local choice = ui.ask_choice({"进入", "离开", "等待"})
if choice == 1 then
    -- 进入
end
```

---

## 数据读写类 API

### data.get_chara(id)
获取角色数据。

**参数：**
- `id` (string): 角色ID

**返回：**
- `table` or `nil`: 角色数据

---

### data.set_stat(target, stat, value)
设置属性值。

**参数：**
- `target` (string): 目标 ("player" 或角色ID)
- `stat` (string): 属性名称
- `value` (number): 属性值

**示例：**
```lua
data.set_stat("player", "hp", 100)
data.set_stat("reimu", "relation", 10)
```

---

### data.get_flag(namespace, key, default?)
获取Flag值。

**参数：**
- `namespace` (string): 命名空间
- `key` (string): Flag键
- `default` (any, optional): 默认值

**示例：**
```lua
local completed = data.get_flag("story", "intro_done", false)
```

---

### data.set_flag(namespace, key, value)
设置Flag值。

**参数：**
- `namespace` (string): 命名空间
- `key` (string): Flag键
- `value` (any): Flag值

**示例：**
```lua
data.set_flag("story", "intro_done", true)
data.set_flag("char:reimu", "met_player", true)
```

---

## 工具类 API

### util.random(min, max)
获取随机数。

**参数：**
- `min` (number): 最小值
- `max` (number): 最大值

**返回：**
- `number`: 随机整数

---

### util.log(message)
输出日志。

**参数：**
- `message` (string): 日志消息

---

## 世界状态 API

### world.get_day()
获取当前天数。

**返回：**
- `number`: 当前天数

---

### world.set_day(day)
设置当前天数。

**参数：**
- `day` (number): 天数

---

### world.get_location()
获取当前位置。

**返回：**
- `string`: 当前位置ID

"""
        return doc
