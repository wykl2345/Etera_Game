# Etera_Game 重构架构设计 v2 — 前后端分离 + Web 渲染

> 状态: 已定稿 | 技术栈: Python 3.12 (asyncio) + Vue 3 + Vite + WebSocket
> 关联: `DSL.txt`(40 指令契约) / `docs/requirements.md`(PRD) / `CONTEXT.md`(领域词汇) / v1 文档与源码见 `docs/archive/v1/` 与 git tag `pre-web-refactor`

---

## 一、背景与目标

### 1.1 v1 的问题

v1 是 Python + PySide6 桌面应用。**引擎核心（Lua 沙箱、事件总线、状态管理、存档）完成度 100%，但渲染/布局层是最大负担**：

- 状态栏显示时机、UI 模式栈、选项嵌入文本流、立绘淡入淡出——全是 Qt 布局和信号槽的苦差事
- 嵌套 `QEventLoop` 实现脚本暂停/恢复，脆弱且难调试
- 素材目录全空，UI 打磨（Phase 1-4）大量积压

### 1.2 v2 的目标

1. **前后端分离**：浏览器负责一切渲染与排版，引擎专注游戏逻辑
2. **内容资产零迁移**：`Data/`（Lua 脚本 + YAML 角色）、`DSL.txt`（40 指令契约）原样复用，Mod 生态不受影响
3. **性能预留**：未来内嵌小游戏（杀戮尖塔式肉鸽），前端渲染层需支持独立 Canvas 挂载
4. **上下文友好**：源码删除（git tag `pre-web-refactor` 留档），仓库以文档 + 内容资产为主

---

## 二、技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 后端 | Python 3.12 + asyncio | 引擎核心复用 v1 设计，lupa 沙箱保留 |
| 通信 | WebSocket (JSON) | 双向：引擎推 UI 指令，前端回传玩家输入 |
| WS 框架 | `websockets` 或 FastAPI | 轻量优先，暂定 `websockets` 库 |
| 前端 | Vue 3 + Vite | 主框架；小游戏走独立 Canvas 层 |
| 前端状态 | Pinia | uiMode / gameState / statusBar |

---

## 三、架构总览

```
┌─ 浏览器（渲染层）───────────────────────────────────────┐
│  Vue 3 前端                                              │
│  文本流 │ 选项 │ 立绘/背景 │ 状态栏 │ 主菜单 │ 设置/存档    │
│  小游戏层（Canvas 2D 独立渲染循环，与主 UI 解耦）          │
└──────────────▲──────────────────────────────────────────┘
               │ WebSocket（JSON 指令/事件）
┌──────────────┴──────────────────────────────────────────┐
│ Python 后端（游戏逻辑，无 GUI）                           │
│  ┌────────────────────────────────────────────────────┐  │
│  │ WS 网关（会话管理 / 指令路由 / requestId 匹配）       │  │
│  └────────────────┬───────────────────────────────────┘  │
│  ┌────────────────▼───────────────────────────────────┐  │
│  │ 脚本调度器 (asyncio) ←→ Lua 沙箱 + API Bridge(40)  │  │
│  └──────┬────────────────────────┬───────────────────┘  │
│  事件总线 │        GameContext    │  SaveManager         │
│         │        (分层命名空间)   │  (版本化 JSON)        │
└─────────┴────────────────────────┴──────────────────────┘
```

**核心转变**：v1 的 `ScriptRunner ↔ Qt Widgets 信号/槽` 变成 `ScriptRunner ↔ WS 网关 ↔ Vue 组件`。

---

## 四、通信协议（前后端契约）

### 4.1 消息方向

| 方向 | 类型 | 示例 |
|---|---|---|
| 引擎 → 前端（推送） | `ui.*` 指令、`status.update`、`event.log` | `ui.text`、`ui.show_image`、`status.sync` |
| 前端 → 引擎（输入） | 玩家动作 | `choice.made`、`input.submit`、`minigame.result`、`game.start`、`game.day_advance`、`game.save`、`game.emit_event` |
| 引擎 → 前端（回执） | 动作结果 | `save.result`、`load.result`、`event.result`（均带 `ok`/`reason`） |

### 4.2 消息结构

```json
// 同步推送（不阻塞脚本）
{ "type": "ui.text", "payload": { "text": "灵梦在咖啡店门口等着你。", "color": "white", "bold": false } }

// 阻塞式指令（脚本挂起，等玩家输入）
{ "type": "ui.ask_choice", "requestId": "req-1", "payload": { "options": ["进去打招呼", "假装没看见"] } }

// 前端回传（恢复脚本协程）
{ "type": "choice.made", "payload": { "requestId": "req-1", "index": 1 } }
```

### 4.3 requestId 机制

- **同步 API**（`ui.text`、`ui.show_image`、`data.set_stat`…）→ 直接推送，无回执
- **阻塞 API**（`ui.ask_choice`、`ui.ask_input`）→ 发送后挂起 Lua 协程，`requestId` 对应的 `asyncio.Future` 等待前端回传，收到后恢复

### 4.4 完整映射

53 个 Lua API → WS 消息的完整对照表以 `DSL.txt` 为准，此处列典型映射：

| Lua API (DSL.txt) | 方向 | WS 消息 |
|---|---|---|
| `ui.text` / `ui.clear` | → | `ui.text` / `ui.clear` |
| `ui.show_image` / `hide_image` | → | `image.show` / `image.hide`（附 URL） |
| `ui.show_character` / `hide_character` | → | `character.show` / `character.hide` |
| `ui.play_music` / `play_sound` | → | `audio.play`（浏览器 WebAudio） |
| `ui.ask_choice` | 请求-响应 | `ui.ask_choice` ↔ `choice.made` |
| `ui.ask_input` | 请求-响应 | `ui.ask_input` ↔ `input.submit` |
| `minigame.start` | 请求-响应 | `minigame.start` ↔ `minigame.result`（结果回传 Lua） |
| `world.*` / `data.*` | 服务端内部 | 无消息，状态变更后推 `status.sync` |
| `event.emit` | 服务端内部 | 同步调用所有监听者（含 Lua handler），payload 装进 `ctx.data` |
| 前端主动触发剧本 | ← | `game.emit_event{event}` → 后端 `bus.emit(event)` → `event.result` 回执 |

### 4.5 存读档一致性约束

**只有脚本空闲时才能存读档**（`_persist_blocked`，服务端强制，前端按钮同步置灰）：

- 拒绝条件：`scheduler.is_waiting()`（有 `ask_choice`/`ask_input`/`minigame.start` 挂起）
- 拒绝时返回 `save.result` / `load.result`，`ok=false` 并附 `reason`

原因：存档只序列化服务端 `GameContext`（world/player/characters/flags），而对话文本、立绘、
背景、选项全在前端 store 里，服务端不知情。中途存档会存出"数据在新位置、画面在半截"的
不一致档，读回来也无法对齐 —— 因为 **Lua 脚本的执行位置无法序列化**。

> 即"存读档功能在触发对话前使用"。

### 4.6 Hub（行动枢纽）—— 系统界面

进入游戏后不是直接播对话，而是先到 **Hub**：一个全屏行动菜单，玩家自己决定做什么。
解决的是"剧本强推对话、玩家没有主动权"的问题。

Hub 上两类按钮：

| 类别 | 来源 | 例子 |
|---|---|---|
| **游戏级按钮** | 引擎固定 | 下一天 / 保存 / 读取 / 设置 / 自检 / 主菜单 |
| **角色行动按钮** | **剧本注册**（`hub` 字段） | 灵梦→聊聊、灵梦→一起修行、魔理沙→聊聊 |

角色按钮的可用性由**数值条件**判定，不满足时置灰并给出原因：

```lua
hub = {
    char = "reimu",              -- 归属角色（显示在哪张角色卡下）
    label = "一起修行",            -- 按钮文案
    order = 20,                  -- 同角色内排序
    require_relation = 10,       -- 好感 < 10 时锁定（前端置灰 + 原因）
    require_flag = "story.intro_completed",   -- 也可用 flag 条件
}
```

协议：

| 消息 | 方向 | 说明 |
|---|---|---|
| `game.hub` | 前端 → 后端 | 进入 Hub 时拉取按钮列表 |
| `hub.buttons` | 后端 → 前端 | `{characters:[{char_id,name,relation,location}], buttons:[{char,label,event,order,available,reason}]}` |
| `game.emit_event{event}` | 前端 → 后端 | 点角色按钮 → 触发该剧本 |
| `event.done` | 后端 → 前端 | 剧本（含阻塞交互）播完 → 前端回 Hub 并刷新 |

> 多选角色（一次对多个角色发起行动）暂未做，数据结构上 `buttons` 已按 `char` 分组、
> 前端 `hubSelectedChar` 是单值 —— 改成 `string[]` 即可扩展。

### 4.6.0 时间流转

一天四个时段：`morning → afternoon → evening → night`。

- **角色行动**（Hub 上的剧本按钮）每执行一次推进一个时段；
  移动、购物、查看信息等系统操作不耗时
- 推进到 `night` 就停住 —— 夜里可以继续行动（剧情需要），但时间不再前进
- **睡觉**（`game.sleep`，仅 `sleep: true` 的场景）→ 回满体力 + 进入下一天 + 重置到 morning
- `dawn` 是剧本专用时刻（如日出场景），不参与日常推进

因此 `hub.require_time = "night"` 这类条件有了实际意义：一天里只有推进到夜里才出现。

**物品分类与使用**（`Data/items/items.yaml`）：

```yaml
glowing_mushroom:
  name: 发光蘑菇
  category: item        # item 普通 / equip 装备 / skill 技能 / key 重要物品
  usable: true
  use_effects:
    - { stat: stamina, delta: 6 }
    - { stat: hp, delta: -3, chance: 0.2 }   # 概率副作用：吃坏肚子
```

- `game.use_item{item}` → 按顺序应用效果（`stat`/`delta`/`chance`/`flag`），消耗 1 个
- 概率项（`chance`）用于随机副作用；省略即必定触发
- 背包面板按分类分页显示，`usable: false` 的物品显示「不可使用」

### 4.6.1 场景 / 行动成本

**场景（Scene）** 是两级结构：区域（region）→ 地点（scene），定义在
`Data/config/scenes.yaml`，启动时由 `SceneRegistry` 加载。

移动可达规则：
1. **同区域**内任意地点互通（自宅 ⇄ 市集）
2. **相邻区域**的地点才能跨区去（人间之里 → 博丽神社 / 魔法森林）

```yaml
regions:
  human_village: { name: 人间之里, adjacent: [shrine, forest] }
scenes:
  home:   { name: 自宅, region: human_village, sleep: true, background: home }
  market: { name: 市集, region: human_village, shop: village_market, background: market }
```

`background` 指向 `resources/images/backgrounds/{id}.png`。`game.move` / `game.home` 成功时后端
立即推送 `ui.background_set`，Hub 也渲染当前地点背景；不再等剧本里的 `ui.set_background`。

Hub 的「移动」按 `same_region` 标记分两组显示：「本区域内」/「前往其他区域」。

**物品与商店** 数据驱动（`Data/items/items.yaml` + `Data/shops/shops.yaml`）：

```yaml
# items.yaml
煎茶: { name: 煎茶, price: 30, gift_value: 5 }
# shops.yaml
shops:
  village_market: { name: 人间之里的市集, items: [煎茶, 团子] }
```

- 地点配了 `shop:` 才在 Hub 出现「购物」
- 商品价格 = 物品基准价 × 商店 `markup`（默认 1.0），方便不同商店定价
- 送礼是引擎通用行动（不占剧本按钮）：`game.gift{char,item}` → 按 `gift_value` 加好感

协议：`game.shop` → `shop.data`；`game.buy{item}` → `buy.result`；
`game.gift{char,item}` → `gift.result`；`game.inventory` → `inventory.data`。

Hub 渲染规则：

| 元素 | 规则 |
|---|---|
| 角色卡片 | 只显示 `location == 玩家位置` 的角色 |
| 角色行动按钮 | 同理，不同场景的角色按钮一律不出现 |
| 移动 | 只列出相邻场景；`game.move{scene}` |
| 睡觉 | 只在 `sleep: true` 的场景可用；`game.sleep`（回满体力 + 推进一天） |

**行动成本**由剧本在 `hub` 里声明，引擎负责判定与扣除：

```lua
hub = { char = "reimu", label = "一起修行",
        stamina_cost = 20,    -- 体力不足 → 变灰；执行后引擎扣除
        daily_limit = 1 }     -- 当天用完 → 变灰；按天隔离，跨天自动恢复
```

计数存于 `global_flags` 的 `_action` 命名空间，键为 `{event}:{day}` ——
用天数做键使"每天重置"无需额外清理逻辑。

> 判定语义：**条件不满足 → 隐藏**（好感/flag/跨场景），
> **暂时不可用 → 变灰**（体力不足/次数用完）。前者是"还没解锁"，后者是"现在做不了"。

### 4.7 对话快照（读档还原画面）

光存数据不够：画面（文本流/背景/立绘）全在前端 store，只 `deserialize` 数据会导致
读档后文本区只剩空占位 `——`、背景空、立绘空。

做法：存档额外写入 `dialogue` 段 —— 存档点所属事件发出的**画面类消息**原始列表：

```json
"dialogue": [
  {"type": "ui.clear", "payload": {}},
  {"type": "ui.background_set", "payload": {"name": "shrine", "transition": "fade"}},
  {"type": "ui.text", "payload": {"text": "――幻想乡，一个被遗忘的世界。", "color": "white", "bold": true}},
  {"type": "ui.character_show", "payload": {"char_id": "reimu", "expression": "normal"}}
]
```

- **记录点**：`DialogueRecorder` 包装 `WSOutput`，旁路保存 `ui.text` / `ui.clear` /
  `ui.background_set` / `ui.character_show` / `ui.character_hide` / `ui.image_*`
- **清空时机**：每次触发事件前 `begin()`（`game.start` / `day_advance` / `emit_event` /
  `on_load`），所以快照 = **最近一个事件的完整对话**，与"存档点在事件边界"一致
- **读档重放**：`load.result` 带回 `dialogue`，前端 `restoreDialogue()` 重建
  `textFlow`/`background`/`characters`；期间置 `restoring=true`，TextFlow 直接把快照
  全文铺满而**不逐字重播**
- **兼容**：老存档无 `dialogue` 字段 → 空列表，前端只清屏（行为同改造前）

> 脚本执行位置（Lua 栈）仍然无法序列化，所以中途存档依旧被禁止。要让读档后
> **继续推进剧情**，仍需要新事件触发；对话快照只负责"画面回到存档那一刻"。

> 设计原则：**状态在服务端，视图在前端**。Lua 改状态后引擎主动推送 `status.sync` 全量快照，前端只做展示，无状态同步回写。

---

## 五、后端设计

### 5.1 调度器改造：QEventLoop → 线程池 + Future

v1 用 Qt 嵌套事件循环暂停/恢复脚本（**v1 无 Lua coroutine**，脚本由 `lua.execute` 同步执行，挂起全在 Python 侧）。v2 的实际实现（`backend/engine/script_runner.py` + `backend/ws_gateway.py`）：

```python
# 脚本在每连接的单 worker 线程池中同步执行（不阻塞 asyncio 主循环）
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="game")
loop.run_in_executor(executor, bundle.bus.emit, "on_game_start")   # 不 await！

# 阻塞指令（脚本线程内）：发消息 + Future 挂起
def ask_choice(self, options: list[str]) -> int:
    req_id = uuid4().hex
    self._pending[req_id] = Future()
    self.output.send({"type": "ui.ask_choice", "requestId": req_id,
                      "payload": {"options": options}})
    return self._pending[req_id].result()   # 阻塞脚本线程

# WS 主循环收到 choice.made → 恢复（线程安全）
def resolve_wait(self, request_id: str, choice_index=None) -> bool:
    if fut := self._pending.get(request_id):
        fut.set_result(choice_index)
```

**关键点（实现中踩过的坑）**：
- `game.start` 触发**不能 await**（`asyncio.to_thread` 会让消息循环停在 `game.start`，脚本挂起等输入时收不到 `choice.made` → 死锁）。必须 fire-and-forget 提交到 executor。
- WS 输出用 `asyncio.Queue` + 单一 sender task 串行发送，避免脚本线程并发 send。
- 每个 WS 连接 = 独立引擎实例（会话隔离，无断线恢复）。

### 5.2 模块复用清单

| v1 模块 | v2 处置 | 说明 |
|---|---|---|
| `event_bus.py` | **复用** | 纯逻辑，零 GUI 依赖 |
| `game_context.py` | **复用** | 分层命名空间状态，序列化不变 |
| `save_manager.py` | **复用** | 版本化 JSON + 迁移链，存档在服务端 `saves/` |
| `sandbox.py` / `api_bridge.py` | **改造** | 阻塞 API 改 async，白名单 40 指令不变 |
| `script_runner.py` | **重写** | 嵌套 QEventLoop → asyncio 协程 |
| `resource_manager.py` | **改造** | 文件路径 → HTTP 静态资源 URL |
| `gui/*` (PySide6) | **废弃** | 全部由 Vue 前端替代 |

### 5.3 会话模型

- 1 个 WS 连接 = 1 个游戏会话；断线重连可恢复（会话按 client_id 暂存）
- 存档仍在服务端（多端同步的天然基础）

---

## 六、前端设计（Vue 3 + Vite）

### 6.1 目录结构

```
frontend/
├── src/
│   ├── main.ts
│   ├── ws/
│   │   └── client.ts          # WS 封装：消息路由、requestId 匹配、断线重连
│   ├── stores/
│   │   ├── game.ts            # 游戏状态（来自 status.sync 快照）
│   │   └── uiMode.ts          # 根界面类型/校验（P3 后不再有模式栈）
│   ├── components/
│   │   ├── TextFlow/          # 终端风格文本流（逐字打印、颜色标签）
│   │   ├── ChoiceMenu/        # 选项按钮（嵌入文本流）
│   │   ├── CharacterLayer/    # 立绘层（淡入淡出）
│   │   ├── BackgroundLayer/   # 背景层
│   │   ├── StatusBar/         # 状态栏（天数/时段/金钱/HP/MP）
│   │   ├── OverlayHost/       # 覆盖层宿主（P3）
│   │   └── MainMenu/          # 主菜单
│   ├── overlays/              # 覆盖层模块注册表（小游戏等）
│   └── games/                 # 小游戏 Canvas 组件
```

### 6.2 UI 状态机（根界面 + Overlay Host + 系统面板）

P3 起 UI 分成三层；覆盖层不再是“伪装成根界面的模式”，主界面始终挂载：

| 层 | 状态 | 取值 | 说明 |
|---|---|---|---|
| **根界面** | `uiMode` | `main_menu` / `hub` / `game` | 唯一的页面级切换 |
| **覆盖层** | `overlay` | `{ id, moduleId, input, requestId }` | 独立 UI 模块（小游戏是第一个），覆盖在根界面上 |
| **系统面板** | `panel` | save / load / settings / characters / shop / gift / inventory | 悬浮在当前界面上，**不改 `uiMode`** |

约束（`frontend/src/stores/uiMode.ts` + `stores/game.ts`）：

1. 根切换统一走 `resetMode()`；没有模式栈，也没有“返回到上一模式”的隐式回退。
2. 覆盖层用 `openOverlay()` 打开；同一时间只允许一个；打开/关闭不改变 `uiMode`。
3. 模块通过 `complete(result)` / `cancel()` 交回结果；store 负责幂等关闭、`requestId` 回传与
   **实例 id 校验**（旧模块的迟到回调不能关闭新覆盖层）。
4. 根切换与覆盖层打开/关闭都写入最近 200 条转移日志（`action: reset / overlay-open / overlay-close`，
   带 `overlay.id/moduleId`）；`window.__eteraUiLog` 可导出，生产环境
   `localStorage.etera.uiDebug=1` 打印控制台。
5. 异步消息带界面代际/模式校验：读档用 `pendingLoadEpoch`，剧本结束用 `pendingEvent`
   （事件名 + 代际），睡觉/`minigame.start` 校验当前模式；迟到消息直接丢弃。
6. 运行时遇到未知根模式，渲染「界面状态异常」恢复页（回行动界面 / 回主菜单），不再静默空壳。

模块注册表：`frontend/src/overlays/index.ts`（当前只有 `minigame` → `MinigameHost`）。
决策：`docs/adr/0008-ui-state-machine.md`、`docs/adr/0009-overlay-host.md`；
回归用例：`frontend/src/stores/game.test.ts`。

### 6.3 终端风格主题

- CSS 变量定义暗色主题：`--bg` / `--fg` / `--accent`，等宽字体
- 选项嵌入文本流、逐字打印、颜色标签 → 全部 CSS/JS 动画，不再依赖 Qt

### 6.4 小游戏扩展（性能约束）

- 小游戏 = Overlay Host 的独立模块（`overlays/index.ts` 注册），渲染组件在 `games/`，
  自有 `requestAnimationFrame` 渲染循环；主界面保持挂载
- Vue 只做外壳与状态桥接（进入/退出模式、得分回写 GameContext）
- 卡牌/肉鸽战斗逻辑全部 Canvas 2D 实现，主框架零干扰——**这是选 Vue 而非游戏引擎的原因：主 UI 是文本冒险，小游戏是附加能力，两者解耦**

---

## 七、仓库目录结构（v2）

```
EE1/
├── CONTEXT.md                   # 领域词汇表（统一语言）
├── DSL.txt                      # Mod 契约（40 指令，前后端协议基准）
├── backend/                     # Python 游戏逻辑服务
│   ├── engine/                  # 沙箱/调度/事件/状态（按本文档重写）
│   ├── ws_gateway.py            # WebSocket 网关
│   ├── main.py                  # 启动入口
│   └── requirements.txt
├── frontend/                    # Vue 3 + Vite + TS
│   ├── src/…                    # 见 6.1
│   └── package.json
├── Data/                        # 共创区（复用，Lua + YAML 原样保留）
│   ├── characters/  scenarios/  config/  items/  ui_themes/
├── resources/                   # 素材（经 HTTP 静态服务提供给前端）
│   ├── images/  audio/  fonts/
└── docs/                        # 文档体系（agent 开发的事实来源）
    ├── architecture.md          # 本文档：架构 + WS 协议
    ├── requirements.md          # PRD：Phase 1-4 需求条目 + 验收标准
    ├── references.md            # 官方文档链接 + 版本坑位 + v1 源码查阅
    ├── adr/                     # 决策记录 0001-0006
    └── archive/v1/              # v1 归档：4 份文档 + status-bar-mode-stack PRD
```

---

## 八、迁移路线图

| Phase | 内容 | 验收标准 |
|---|---|---|
| **0** | 环境迁移 WSL + 文档梳理（本阶段） | ✅ 已完成：WSL 环境、git 留档、架构定稿 |
| **1** | 后端引擎核心重写：沙箱 + 调度器 + 事件总线 + 状态 + 存档 | 单元测试通过（复用 v1 测试用例思路，见 `pre-web-refactor` 的 tests/） |
| **2** | WS 网关 + 最小前端（文本流 + 选项 + 主菜单） | 浏览器跑通序章 `Data/scenarios/story/intro.lua` |
| **3** | 状态栏 / 立绘 / 背景 / 存档界面（模式栈落地） | 咖啡店、蘑菇事件完整可玩 |
| **4** | 打磨：逐字打印、主题、设置面板 + 小游戏 Canvas 实验 | 小型肉鸽原型挂载成功 |

---

## 九、决策记录 (ADR)

| # | 决策 | 理由 |
|---|---|---|
| 1 | 源码删除，git tag `pre-web-refactor` 留档 | 防止源代码污染 LLM 上下文；文档足够详尽可重写 |
| 2 | 后端保留 Python | 引擎核心（沙箱/事件/状态/存档）设计可复用，迁移成本最低 |
| 3 | 前端 Vue 3 + Vite | 用户选型；轻量、中文生态好 |
| 4 | 小游戏走独立 Canvas 层 | 性能硬约束，与主框架解耦 |
| 5 | 状态在服务端、视图在前端 | 单方向状态流，避免双端状态同步复杂度 |
| 6 | 协议以 DSL.txt 为基准 | 40 指令不变，Mod 生态零迁移 |

