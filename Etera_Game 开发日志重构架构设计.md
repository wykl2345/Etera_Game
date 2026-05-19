# Etera_Game 开发日志重构架构设计

## 一、核心设计哲学调整

首先明确一个重要的设计转变：

> **从"Python脚本热加载"→ "DSL解释器 + 受控API"**

引擎只暴露白名单指令集，mod作者用受限脚本语言创作，彻底解决安全问题。市面上可以直接嵌入的成熟选择：

| 脚本语言             | 特点             | 适合场景       |
| -------------------- | ---------------- | -------------- |
| **Lua** (via `lupa`) | 性能好，沙箱成熟 | 推荐首选       |
| **Ink**              | 专为叙事游戏设计 | 剧情分支复杂时 |
| **自定义DSL**        | 完全可控         | 需要开发成本   |

后续设计以 **Lua** 为例展开，思路通用。

------

## 二、重构后的整体架构

```
┌─────────────────────────────────────────────────────┐
│                   My Emuera Engine                  │
│                                                     │
│  ┌──────────┐    ┌──────────┐    ┌───────────────┐  │
│  │  GUI层   │◄──►│  引擎核心 │◄──►│   脚本沙箱层  │  │
│  │(PySide6) │    │  (Core)  │    │  (Lua/DSL)    │  │
│  └──────────┘    └──────────┘    └───────────────┘  │
│                       │                             │
│              ┌────────┼────────┐                    │
│              ▼        ▼        ▼                    │
│         ┌────────┐ ┌──────┐ ┌──────┐               │
│         │状态管理 │ │事件总线│ │资源管理│              │
│         └────────┘ └──────┘ └──────┘               │
└─────────────────────────────────────────────────────┘
         ▲                           ▲
    ┌────┴─────┐               ┌─────┴────┐
    │  /Data   │               │/Resources│
    │ (共创区)  │               │ (素材区)  │
    └──────────┘               └──────────┘
```

------

## 三、目录结构重设计

```
/MyEmueraGame
│
├── /core                        # 引擎层（用户不动）
│   ├── main.py                  # 启动入口
│   ├── /gui
│   │   ├── window_manager.py    # 主窗口管理
│   │   ├── log_widget.py        # 文本Log组件
│   │   ├── choice_widget.py     # 选项按钮组件
│   │   └── image_widget.py      # 图片显示组件
│   │
│   ├── /engine
│   │   ├── script_runner.py     # 协程调度器（核心）
│   │   ├── event_bus.py         # 事件总线
│   │   ├── api_bridge.py        # 暴露给脚本的API白名单
│   │   └── sandbox.py           # Lua沙箱初始化
│   │
│   ├── /state
│   │   ├── game_context.py      # 运行时状态
│   │   ├── character_model.py   # 角色数据模型
│   │   └── save_manager.py      # 存档管理（JSON）
│   │
│   └── /resource
│       ├── resource_manager.py  # 资源统一加载
│       └── cache.py             # 资源缓存
│
├── /data                        # 共创区（Mod作者的世界）
│   ├── /config
│   │   └── game_settings.yaml   # 全局配置
│   │
│   ├── /characters              # 角色定义
│   │   ├── reimu.yaml
│   │   └── marisa.yaml
│   │
│   ├── /events                  # 事件脚本（Lua）
│   │   ├── /daily               # 日常事件
│   │   ├── /story               # 主线事件
│   │   └── /system              # 系统级逻辑（回合结算等）
│   │
│   ├── /items                   # 物品定义
│   └── /ui_themes               # 界面主题配置（可扩展）
│
└── /resources
    ├── /images
    ├── /audio
    └── /fonts
```

------

## 四、核心模块详细设计

### 模块 1：协程调度器 `script_runner.py`

**这是整个引擎最核心的部分**，解决"等待玩家输入时暂停脚本"问题。

```
设计模式：生产者-消费者 + 协程

脚本执行流：

  [Lua脚本]          [调度器]            [GUI]
     │                  │                  │
     │── show_text() ──►│── emit信号 ──────►│ 显示文字
     │                  │                  │
     │── ask_choice() ──►│── 暂停脚本 ──────►│ 生成按钮
     │                  │◄── 用户点击 ───────│
     │◄── resume(选择) ──│                  │
     │                  │                  │
     │── end_event() ──►│── 通知EventBus ──►│ 触发下一事件
```

**关键设计决策：** Lua协程（`coroutine.yield`）天然支持这个模式，和Python的调度器可以无缝对接，这也是选Lua的重要原因之一。

------

### 模块 2：事件总线 `event_bus.py`

解决多Mod之间互相感知的问题，也是触发剧情的统一入口。

```
事件分两类：

【系统事件】由引擎自动emit          【游戏事件】由脚本主动emit
─────────────────────────          ──────────────────────────
on_game_start                       custom:first_meeting
on_day_begin / on_day_end           custom:love_max
on_save / on_load                   custom:dungeon_clear
on_character_stat_changed
```

**订阅关系示意：**

```
event_bus
    │
    ├── "on_day_end"
    │       ├── system/daily_calc.lua   (结算体力、金钱)
    │       ├── events/daily/random.lua (随机日常事件)
    │       └── events/story/check.lua  (检查主线触发条件)
    │
    └── "on_character_stat_changed"
            └── ui/status_bar.lua       (刷新状态栏显示)
```

这样每个Mod只需声明自己监听哪些事件，完全解耦。

------

### 模块 3：状态管理 `game_context.py`

从扁平字典升级为**分层命名空间**：

```
GameContext
│
├── world                    # 世界级状态
│   ├── day: int
│   ├── time_of_day: enum    (morning/afternoon/night)
│   └── location: str
│
├── player                   # 玩家状态
│   ├── stats: StatBlock     (hp/mp/money...)
│   └── inventory: Inventory
│
├── characters               # 所有角色状态 (id → CharaState)
│   ├── "reimu"
│   │   ├── stats: StatBlock
│   │   ├── flags: FlagStore  ← 角色专属开关，命名空间隔离
│   │   └── relation: int
│   └── "marisa"
│       └── ...
│
└── global_flags             # 全局剧情开关
    ├── namespace: "core"    ← 引擎保留
    └── namespace: "mod_xxx" ← 各Mod自己的命名空间
```

**Flag命名空间**是多Mod共存的关键，防止不同Mod的变量互相污染。

------

### 模块 4：API Bridge `api_bridge.py`

这是安全边界的核心——**Lua脚本只能调用这里白名单里的函数**，任何文件系统、网络操作都无法触及。

```
暴露给脚本的API分组：

【UI类】
  ui.text(str, color?, bold?)       # 输出文字
  ui.clear()                        # 清空Log
  ui.show_image(name, position?)    # 显示图片
  ui.play_sound(name)               # 播放音效
  ui.ask_choice(options[])          # 等待选择（会触发yield）
  ui.ask_input(prompt)              # 等待文字输入

【数据读写类】
  data.get_chara(id)                # 获取角色数据
  data.set_stat(chara_id, key, val) # 修改角色属性
  data.get_flag(namespace, key)     # 读取Flag
  data.set_flag(namespace, key, val)# 写入Flag（限自己的命名空间）

【事件类】
  event.emit(name, payload?)        # 触发自定义事件
  event.after_days(n, callback)     # n天后触发

【工具类】
  util.random(min, max)             # 随机数
  util.log(msg)                     # 调试输出（不影响游戏UI）
```

------

### 模块 5：存档管理 `save_manager.py`

放弃 pickle，采用**版本化JSON存档**：

```
存档结构：

save_slot_1.json
{
  "meta": {
    "version": "1.2.0",       # 引擎版本
    "save_time": "...",
    "playtime": 3600
  },
  "world": { "day": 42, ... },
  "player": { ... },
  "characters": { ... },
  "flags": { ... }
}
```

版本迁移链：`migrate_1.0_to_1.1.py`, `migrate_1.1_to_1.2.py`

存档加载时自动按版本链升级，保证兼容性。

------

## 五、模块依赖关系总览

```
         ┌─────────────────────────────────────┐
         │           GUI Layer                 │
         │  LogWidget  ChoiceWidget  ImgWidget  │
         └──────────────┬──────────────────────┘
                        │ 信号/槽
         ┌──────────────▼──────────────────────┐
         │         Script Runner               │◄──── Lua Sandbox
         │      (协程调度器，引擎心脏)            │      (api_bridge)
         └──────┬──────────────┬───────────────┘
                │              │
    ┌───────────▼──┐    ┌──────▼──────────┐
    │  Event Bus   │    │  Game Context   │
    │  (事件总线)   │    │  (状态管理)      │
    └──────────────┘    └──────┬──────────┘
                               │
                        ┌──────▼──────────┐
                        │  Save Manager   │
                        │  (JSON存档)     │
                        └─────────────────┘
```

------

## 六、Mod 开发者视角（共创体验）

从Mod作者的角度，他们看到的是这样一个极简世界：

```lua
-- /data/events/daily/coffee_shop.lua

-- 声明：这个脚本监听哪些事件
Event.on("on_day_begin", function()
    -- 只在第5天之后、好感度>20时触发
    if world.day < 5 then return end
    if data.get_chara("reimu").relation < 20 then return end

    ui.show_image("reimu_normal")
    ui.text("灵梦在咖啡店门口等着你。", "white")

    local choice = ui.ask_choice({"进去打招呼", "假装没看见"})

    if choice == 1 then
        ui.text("灵梦：来得正好，帮我付咖啡钱。", "pink")
        data.set_stat("player", "money", -30)
        data.set_stat("reimu", "relation", 5)  -- +5好感
        data.set_flag("coffee_mod", "met_at_cafe", true)
    end
end)
```

**Mod作者完全不需要知道引擎内部怎么运作**，只需要学习这套简单的API。

------

## 七、设计总结

| 模块                 | 解决的问题            |
| -------------------- | --------------------- |
| Lua沙箱 + API Bridge | 安全性，权限可控      |
| 协程调度器           | 脚本暂停/恢复，不卡UI |
| 事件总线             | 多Mod解耦，扩展性     |
| 分层状态 + 命名空间  | 数据不混乱，Mod不冲突 |
| 版本化JSON存档       | 存档兼容性，可迁移    |

这套架构的扩展路径非常清晰：先把协程调度器和API Bridge做扎实，其他模块可以逐步补充，不会互相阻塞。