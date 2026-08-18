# Etera_Game PRD — Phase 1-2（后端引擎 + 最小前端）

> 版本: v1.0 | 状态: 已定稿（grill-with-docs 会话产出）| 关联: `docs/architecture.md` / `docs/references.md` / `CONTEXT.md` / `DSL.txt`

---

## 1. 背景与动机

v1 为 Python + PySide6 桌面应用：引擎核心（Lua 沙箱、事件总线、状态管理、存档）完成度 100%，但 Qt 渲染/布局层成为最大负担（状态栏时机、模式栈、选项嵌入、立绘淡入淡出）。重构目标：

1. **前后端分离**：浏览器负责渲染与排版，引擎专注游戏逻辑
2. **节约 UI 成本 + 现代化**：系统界面（主菜单/设置/存档等）彻底 Web 化重设计
3. **内容资产零迁移**：40 个 Lua 指令（DSL.txt）语义不变，Mod 生态不受影响

---

## 2. 范围

| | 范围 |
|---|---|
| **Phase 1** | 后端引擎核心重写 + WS 网关（不含存档，见 §5.6） | ✅ 已完成（commit 3a828d8） |
| **Phase 2** | 最小前端（Vue3 + TS）+ 完整跑通仓库 3 个剧本 | ✅ 已完成（commit 9c62de2） |
| **Phase 3** | 状态栏/立绘/背景/存档界面（模式栈落地） | ✅ 已完成（commit 3ed2335） |
| **Phase 4** | 打磨：逐字打印/设置面板/音频 + 小游戏 Canvas 实验 | ✅ 已完成（commit 25acf53） |
| 范围外 | 存档系统、状态栏打磨、设置/调试面板、小游戏（Phase 3-4） |

---

## 3. 非功能需求

| # | 约束 | 等级 |
|---|---|---|
| NFR-1 | **上下文友好**：代码与文档保持轻量，避免大文件 | 软 |
| NFR-2 | **Mod 兼容**：40 个 Lua 指令语义与 v1 完全一致，DSL.txt 不变更 | **硬** |
| NFR-3 | **协议一致性**：WS 消息结构有单一事实来源（TS 类型 + Python 侧校验），防两端漂移 | **硬** |
| NFR-4 | **性能**：文本冒险 UI 无感知延迟；小游戏 Canvas 独立渲染（60fps） | 软 |
| NFR-5 | **可测试性**：引擎核心无 GUI 依赖，全部可单测 | 软 |

---

## 4. 术语

见 `CONTEXT.md`。关键区分：**Event**（事件总线消息）/ **Scenario**（Lua 剧本）/ **Scene**（玩家情境）；**叙事界面**（gal 布局，平移复用）/ **系统界面**（Web 重设计）。

---

## 5. Phase 1 — 后端引擎（Python 3.12 + asyncio）

### 5.1 引擎核心模块

| ID | 需求 | 验收标准 |
|---|---|---|
| P1-01 | Lua 沙箱：固定 `lupa.lua54`，`register_eval=False`、`register_builtins=False`、内存上限；移除 `os`/`io`/`debug`/`loadfile` 等危险全局；`MockLuaRuntime` 降级方案保留 | 沙箱内无法访问文件系统/网络；lupa 不可用时引擎可降级启动 |
| P1-02 | API 白名单：**40 指令（实测，非文档原载 37）**（DSL.txt）语义与 v1 一致；阻塞指令（`ask_choice`/`ask_input`）挂起/恢复语义正确 | ✅ 对照 v1 测试思路逐指令验证通过 |
| P1-03 | 调度器：线程池 + `concurrent.futures.Future` 挂起/恢复（替代 v1 的 Qt 嵌套 QEventLoop；**无 Lua coroutine**，脚本在线程中同步执行） | ✅ 挂起/恢复/中止测试通过 |
| P1-04 | 事件总线：发布-订阅、同步/异步 emit、优先级、事件过滤、一次性订阅、传播停止（对齐 v1 能力） | v1 事件总线测试思路全部通过 |
| P1-05 | 状态管理：GameContext 分层命名空间（world/player/characters/global_flags），`core` 命名空间受保护 | 命名空间隔离测试通过；脚本无法写 `core` |
| P1-06 | 角色模型：YAML 加载（reimu/marisa），与 v1 数据格式兼容 | `Data/characters/*.yaml` 原样加载 |

### 5.2 加载机制

| ID | 需求 | 验收标准 |
|---|---|---|
| P1-07 | Scenario 加载：递归扫描 `Data/scenarios/`（`rglob("*.lua")`）自动注册，无清单文件（沿用 v1 机制）；**`Data/events/` 目录改名 `Data/scenarios/`**（已确认零路径依赖） | 3 个剧本全部注册到事件总线 |

### 5.3 WS 网关与会话

| ID | 需求 | 验收标准 |
|---|---|---|
| P1-08 | WebSocket 网关（`websockets>=14`，新版 asyncio API：`from websockets.asyncio.server import serve`，单参数回调）：引擎 → 前端推送 `ui.*` 指令；前端 → 引擎 `choice.made`/`input.submit`；阻塞指令带 `requestId` | 握手、消息路由、`requestId` 匹配正确；v1 40 指令 → WS 消息映射见 `docs/architecture.md` §4 |
| P1-09 | 会话模型：单连接单会话，**无断线恢复**（断线即结束本局）；存档服务端化（Phase 3 落地） | 断线后服务端会话清理，无泄漏 |
| P1-10 | 静态资源服务：`resources/` 经 HTTP 提供给前端（立绘/背景/音频 URL），资源缺失返回占位 | 前端可按 URL 加载图片；缺失资源不崩溃 |

### 5.4 后端工程

| ID | 需求 | 验收标准 |
|---|---|---|
| P1-11 | 目录结构 `backend/engine/` + `ws_gateway.py` + `main.py`；依赖 `lupa==2.8`、`websockets>=14`、`PyYAML` | `python backend/main.py` 启动服务；单元测试通过 |

### 5.5 Phase 1 验收（✅ 已完成）

- ✅ 引擎核心 5 模块单元测试全部通过（**88 项全绿**，复用 v1 测试思路）
- ✅ `python backend/main.py` 启动，WS 握手成功（HTTP 101）
- ✅ 静态资源 HTTP 可达（缺失资源返回 404 不崩溃）
- ✅ 端到端：加载 3 剧本 → 触发 `on_game_start` → 序章挂起等选项 → `choice.made` 恢复 → Flag/好感度生效

### 5.6 存档系统（✅ Phase 3 已完成）

- ✅ SaveManager v2（`backend/engine/save_manager.py`）：版本化 JSON（2.0.0）+ 迁移链（1.0→1.1→1.2→1.3→2.0.0，load 后写回）+ 原子写入 + 自动备份（≤5）+ 20 槽位 + 槽 0 快速存档
- ✅ 协议：`game.save/load/quick_save/quick_load/list_saves` → `save.result/load.result/saves.list`
- ✅ `status.sync` 推送：api_bridge 写操作后自动推全量快照（状态栏数据源）
- 断线恢复/会话暂存 → 未来评估（体验优化，已记录意图）

---

## 6. Phase 2 — 最小前端（Vue 3 + Vite + TS）

### 6.1 工程初始化

| ID | 需求 | 验收标准 |
|---|---|---|
| P2-01 | Vite 项目 `frontend/`（模板 `vue-ts`），Pinia 状态管理；**WSL 需先安装 Node ≥22.12**（见 `docs/references.md` §三.4） | `npm run dev` 启动；`vue-tsc` 类型检查通过 |
| P2-02 | WS 客户端封装 `src/ws/client.ts`：连接、消息路由、`requestId` 匹配、自动重连（游戏内无恢复，仅网络层重连提示） | 与后端握手；消息类型定义与 `docs/architecture.md` §4 协议一致（NFR-3） |

### 6.2 叙事界面组件（gal 布局平移）

| ID | 需求 | 验收标准 |
|---|---|---|
| P2-03 | 文本流 `TextFlow`：终端风格（等宽字体、暗色、颜色标签、逐字打印） | `ui.text`/`ui.clear` 正确渲染 |
| P2-04 | 选项 `ChoiceMenu`：选项嵌入文本流，点击回传 `choice.made`（带 `requestId`） | `ask_choice` 全流程（发送→显示→点击→恢复）正确 |
| P2-05 | 背景层 `BackgroundLayer` + 立绘层 `CharacterLayer`：图片显示 + CSS 淡入淡出（`image.show`/`image.hide`/`character.show`/`character.hide`） | 序章立绘/背景调用正确显示；缺失资源显示占位 |
| P2-06 | 输入 `ui.ask_input`（文字输入框，回传 `input.submit`） | 输入流程正确 |

### 6.3 系统界面组件（Web 重设计）

| ID | 需求 | 验收标准 |
|---|---|---|
| P2-07 | 主菜单 `MainMenu`：**现代化 Web 风格**（大标题 + 卡片式选项，CSS 渐变过渡，不依赖美术资源），选项：开始新游戏 / 继续（占位）/ 设置（占位）/ 退出 | 视觉现代化；"开始新游戏"触发 `game.start`，进入叙事界面 |

### 6.4 Phase 2 验收（✅ 已完成）

- ✅ **3 个剧本全部可玩**：`story/intro.lua`（序章，前端联调：挂起→选择→分支→立绘/背景）、`daily/coffee_shop.lua`（后端端到端：好感≥20+day≥5 → 选项 → met_at_cafe flag）、`daily/marisa_mushroom.lua`（前端联调：day_advance 触发 → 3 选项）
- ✅ 日常事件循环：新增 `game.day_advance` 协议消息（day+1 → on_day_end → on_day_begin）
- ✅ 浏览器完整链路：主菜单 → 新游戏 → 序章 → 选项 → Flag 设置 → 日常事件触发（Node e2e 脚本验证 + `npm run build` 通过）

---

## 7. 风险与依赖

| 风险 | 缓解 |
|---|---|
| WSL 无 Node（Vite 8 需 ≥22.12） | Phase 2 前安装（nvm 或 nodesource） |
| lupa Lua 版本漂移（默认导入用最新 Lua） | 固定 `lupa.lua54`（ADR-0004） |
| WS 协议两端漂移 | TS 类型 + Python 校验单一事实来源（NFR-3） |
| 剧本执行与 v1 语义差异 | 对照 `pre-web-refactor` 的 tests 与 DSL.txt 逐指令验证 |

---

## 8. 未来方向（记录，不承诺）

- 断线恢复/会话暂存（体验优化）
- 小游戏（杀戮尖塔式肉鸽）：独立 Canvas 层（ADR-0005）——**Phase 4 已实现原型**：`frontend/src/games/SlimeBattle.vue`（回合制卡牌，纯 Canvas 2D + rAF，与主框架解耦）
- 音频（WebAudio）：**Phase 4 已实现**（`frontend/src/audio.ts`，处理 audio.* 消息，无素材静默）
- 设置面板：**Phase 4 已实现**（`frontend/src/stores/settings.ts` localStorage 持久化：文字速度/逐字开关/字号/音量）

