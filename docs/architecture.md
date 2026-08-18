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
| 前端 → 引擎（输入） | 玩家动作 | `choice.made`、`input.submit`、`game.start`、`game.day_advance`、`game.save` |

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

40 个 Lua API → WS 消息的完整对照表以 `DSL.txt` 为准，此处列典型映射：

| Lua API (DSL.txt) | 方向 | WS 消息 |
|---|---|---|
| `ui.text` / `ui.clear` | → | `ui.text` / `ui.clear` |
| `ui.show_image` / `hide_image` | → | `image.show` / `image.hide`（附 URL） |
| `ui.show_character` / `hide_character` | → | `character.show` / `character.hide` |
| `ui.play_music` / `play_sound` | → | `audio.play`（浏览器 WebAudio） |
| `ui.ask_choice` | 请求-响应 | `ui.ask_choice` ↔ `choice.made` |
| `ui.ask_input` | 请求-响应 | `ui.ask_input` ↔ `input.submit` |
| `world.*` / `data.*` | 服务端内部 | 无消息，状态变更后推 `status.sync` |
| `event.emit` | → | `event.log`（前端日志/调试面板） |

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
│   │   └── uiMode.ts          # UI 模式栈（继承 v1 PRD）
│   ├── components/
│   │   ├── TextFlow/          # 终端风格文本流（逐字打印、颜色标签）
│   │   ├── ChoiceMenu/        # 选项按钮（嵌入文本流）
│   │   ├── CharacterLayer/    # 立绘层（淡入淡出）
│   │   ├── BackgroundLayer/   # 背景层
│   │   ├── StatusBar/         # 状态栏（天数/时段/金钱/HP/MP）
│   │   └── MainMenu/          # 主菜单
│   └── games/                 # 小游戏挂载点（Canvas 组件）
```

### 6.2 UI 模式栈（继承 v1 PRD）

v1 的 `push_mode/pop_mode/reset_mode` 思路在 Web 端天然成立，直接用 Pinia 实现：

| 模式 | 状态栏 | 说明 |
|---|---|---|
| `main_menu` | 隐藏 | 标题界面 |
| `game` | 显示 | 游戏进行中 |
| `settings` | 隐藏 | 设置面板 |
| `save` / `load` | 隐藏 | 存档界面 |
| `character_detail` | 隐藏 | 角色详情弹窗 |
| `minigame` | 隐藏 | 小游戏（预留） |

详见 `docs/archive/v1/status-bar-mode-stack/PRD.md`，规则表可直接照搬。

### 6.3 终端风格主题

- CSS 变量定义暗色主题：`--bg` / `--fg` / `--accent`，等宽字体
- 选项嵌入文本流、逐字打印、颜色标签 → 全部 CSS/JS 动画，不再依赖 Qt

### 6.4 小游戏扩展（性能约束）

- 小游戏 = 独立 Canvas 组件，挂载到 `games/`，自有 `requestAnimationFrame` 渲染循环
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
    ├── requirements.md          # PRD：Phase 1-2 需求条目 + 验收标准
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

