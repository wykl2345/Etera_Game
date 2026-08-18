# Etera_Game 领域词汇表

Etera_Game 是一个 Emuera/ERA 风格的叙事文字冒险游戏引擎，采用前后端分离架构：后端（Python + asyncio）承载游戏逻辑与 Lua 沙箱，前端（Vue 3）负责浏览器渲染。本词汇表定义该领域的统一语言，PRD、代码、注释、Mod 文档必须一致使用。

## 叙事结构

**Event（事件）**:
事件总线上的消息（如 `on_day_begin`、`character_stat_changed`），引擎与模块间的通知机制。
_Avoid_: 剧本、场景

**Scenario（剧本）**:
一段由 Lua 脚本驱动、可播放的完整剧情（对应 v1 的"事件脚本"，文件位于 `Data/scenarios/`）。
_Avoid_: 事件脚本、剧情文件

**Scene（场景）**:
玩家在剧情中经历的单个情境（如"咖啡店场景"），是玩家体验的最小单元。
_Avoid_: 剧情事件

## 共创

**Mod**:
由共创者编写的、通过 Lua 沙箱 API 扩展游戏内容的独立模块。
_Avoid_: 插件、DLC

**共创区 (Data)**:
Mod 作者可自由修改的内容资产目录（角色 YAML、剧本 Lua、配置、物品、主题）。
_Avoid_: 数据区、内容区

## 游戏状态

**Flag（剧情开关）**:
带命名空间的布尔/值开关，记录剧情进度与 Mod 状态（如 `coffee_mod.met_at_cafe`），按命名空间隔离，`core` 命名空间受引擎保护。
_Avoid_: 标记、变量

**关系值 (relation)**:
角色与玩家之间的好感度数值。
_Avoid_: 好感度值、亲密度

**存档 (Save)**:
版本化 JSON 序列化的游戏状态快照，含迁移链与自动备份。
_Avoid_: 记录、进度文件

## 引擎机制

**调度器 (Scheduler)**:
执行 Lua 剧本的协程调度核心，负责"脚本暂停等待玩家输入"的挂起/恢复。
_Avoid_: 脚本运行器、执行器

**API 白名单 (API Bridge)**:
Lua 沙箱中唯一可调用的受限指令集（37 个），Mod 的编程边界。
_Avoid_: 接口层、桥接层
