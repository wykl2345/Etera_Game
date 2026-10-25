# Etera_Game 开发进度记录

> 更新: 2026-08-19 | 状态: 引擎平台完成（Phase 1-4 全达成），进入内容创作阶段

---

## 一、项目概览

Etera_Game 前后端分离重构：Python 引擎核心（Lua 沙箱 + 事件总线 + 状态 + 存档）经 WebSocket 对接 Vue 3 前端（浏览器渲染）。Emuera/ERA 风格叙事文字冒险游戏。

```
✅ Phase 1 后端引擎     ✅ Phase 2 最小前端     ✅ Phase 3 存档/状态栏     ✅ Phase 4 打磨/小游戏
✅ 后端 130 测试全绿    ✅ 前端 type-check + build    ✅ 联调验收（dev.sh 一键启动）
```

## 二、完成度评估

| 模块 | 完成度 | 说明 |
|---|---|---|
| 后端引擎核心 | **97%** | 两级场景（区域→地点）+ 数据驱动物品/商店目录， Lua 沙箱（lupa54 + 安全限制 + Mock 降级）、53 指令 API 白名单、线程池调度器（Future 挂起/恢复）、事件总线（支持剧本声明 priority）、分层状态（core 保护）、剧本加载、GameContext 序列化 |
| 后端存档系统 | **94%** | 版本化 JSON（2.0.0）+ 迁移链（1.0→2.0）+ 原子写入 + 备份 + 20 槽 + 快速存档 + **对话快照**（读档还原文本/背景/立绘）；断线恢复未做（记录意图） |
| WS 网关/协议 | **93%** | 场景移动（`game.move`）/ 睡觉（`game.sleep`）/ 行动成本判定， 单连接单会话、queue 串行发送、requestId 机制、status.sync 推送、存档/小游戏消息、`game.emit_event`（前端主动触发剧本）、存读档一致性校验（对话中拒绝存读档）；无断线重连 |
| 前端叙事界面 | **88%** | 全屏 CG 特写（ui.cg）、行间停顿节奏控制， 文本流（逐字打印 + 段落点击推进 + 快进）、选项、立绘/背景占位、输入、小游戏触发 |
| 前端系统界面 | **88%** | **Hub 行动枢纽**（角色卡片 + 剧本注册的行动按钮 + 数值条件锁定）、主菜单、状态栏、存档界面、设置面板（localStorage） |
| 小游戏 | **60%** | Canvas 独立层架构验证（注册表 + MinigameHost + 结果回传）；仅 1 个原型（史莱姆回合制） |
| 内容资产 | **32%** | 14 个 Lua 剧本：灵梦完整主线（4 段突破 + 送礼 + 闲聊/修行/早晨）、魔理沙基础互动、日常事件、序章、自检：序章 / 咖啡店 / 蘑菇事件 / **早晨问候（每日）** / 演示 + DSL 自检；日常事件链已跑通（day 2 起每天早晨 + day≥3 蘑菇 + day≥5 咖啡店）；美术/音频素材全空（占位显示） |
| 测试 | **95%** | 后端 130 项（事件/状态/调度/存档/WS 端到端 + event payload 回归 + 存读档一致性 + 对话快照 + 日常事件链）；前端无自动化测试（e2e-check.mjs 手工联调脚本） |
| 文档体系 | **90%** | CONTEXT（词汇）/ architecture / requirements（PRD）/ references（坑位）/ ADR×6 / DSL 契约 |

**总体评估**：引擎平台 ~85%，内容创作 ~10%。开发阶段（Phase 1-4）结束，进入内容阶段（写剧本 / 补素材 / 加小游戏）。

## 三、踩坑记录（开发全过程的坑）

### 环境类
| 坑 | 现象 | 解决 |
|---|---|---|
| WSL 大小写敏感 | `data/` vs `Data/`，v1 在 Windows 能跑、WSL 找不到目录 | main.py 默认参数改大写；WSL 开发必须以 ext4 实际目录为准 |
| Node `latest-v2x.x` 目录退役 | v22 目录 404（旧版本线被移除） | 用仍在维护的 LTS 线并写死版本号（v24.19.0） |
| TypeScript 7 与 vue-tsc 不兼容 | `ERR_PACKAGE_PATH_NOT_EXPORTED`（TS7 原生编译器无 ./lib/tsc） | 降 TS 到 5.9.3 |
| create-vite 交互取消 | 非交互终端 "Operation cancelled" | 手工搭建 Vite 工程（模板文件反正要重写） |
| lupa 需 venv | PEP 668 externally-managed 阻止系统级 pip | `.venv` 虚拟环境 |

### lupa / Lua 绑定类
| 坑 | 现象 | 解决 |
|---|---|---|
| LuaTable 无 `.get()` | `globals_.get("math")` 返回 None（在查 Lua 的 "get" 键），安全限制静默失效 | 改用下标 `globals_["math"]` |
| LuaTable 迭代产出键 | `list(table)` 得到 `['1','2','3']` 而非值 | `_to_list` 用 `.values()` |
| Lua table 参数转 dict | `minigame.start(..., {hp=30})` 收到 `{}` | `_to_dict`（keys()/values() 配对） |
| `event.emit` payload 丢失 | Lua handler 读 `ctx.data["score"]` 抛 KeyError，整个剧本中断（后续指令全部不执行） | `_event_emit` 也要用 `_to_dict` —— 此前只修了 `minigame.start`，漏了这一处；已补回归测试 |
| Lua 版本漂移风险 | lupa wheel 内置到 5.5，默认导入跟随升级 | ADR-0004：固定 `import lupa.lua54` |

### 后端 / asyncio 类
| 坑 | 现象 | 解决 |
|---|---|---|
| `asyncio.get_event_loop()` 3.12 弃用 | DeprecationWarning（v1 event_bus 遗留） | v2 用 `get_running_loop()` / `loop.create_future()` |
| websockets 14+ API 变更 | 旧 `(ws, path)` 回调移除、新 asyncio 命名空间 | `from websockets.asyncio.server import serve`，单参数回调 |
| WS 网关 `game.start` await 死锁 | `asyncio.to_thread` 阻塞消息循环，收不到 choice.made | 改为 fire-and-forget 提交 executor（不 await） |
| 单 worker executor 被挂起脚本占用 | 回主菜单后再次 game.start 排队永不执行 → 空对话 | `game.abort` 消息：stop_all 中止挂起脚本释放线程 |
| 挂起中重启/断开 → 日志 ERROR `Future exception was never retrieved` | 选项界面点「开始新游戏」或直接关标签页时后端打印 `ScriptAbortedError` 堆栈（功能正常，纯噪音） | **未修**：脚本线程的 Future 异常无人 retrieve；需在 executor 提交处吞掉/记录已知中止异常 |
| 新游戏不重置状态 | 二次 game.start 时 intro_completed 残留 → 序章不触发 | `reset_game`（stop_all + ctx.reset + 重载角色） |

### 前端 / Vue 类
| 坑 | 现象 | 解决 |
|---|---|---|
| watch 非 deep 数组 push 不触发 | 逐字打印只启动一次，文本全空白（开场剧情"缺失"） | `watch(..., { deep: true })` |
| 段落 confirmed 下标 | 最后一段被 `displayText` 隐藏（`i < confirmed` 判断） | 段完成时计入 confirmed（`confirmed = activeIdx + 1`） |
| 段落等待与逐条到达文本 | 中间有 sleep 的文本段自动跳过点击 | 段完成总是显示 ▼ 等点击（不依赖后续行是否已到） |
| 选项与文本时序 | 选项先弹出 / 选项不出现 | `textIdle` 门控（选项等文本确认后出现）+ activeIdx 完成时重置 |
| 点击区域过窄 | 只能在文本区点击推进 | 全画面点击委托（GameScreen advanceText）+ 交互组件 .stop 防误触 |
| Pinia 泛型索引赋值 | `this[key] = value` TS 报错 | 用 `$patch` |
| 存档界面白色滚动条/横条 | 白底粗轨道 + 不该有的横滚条 | 自定义细线滚动条（透明 track）+ `overflow-x: hidden` |
| 对话中途存档存出半截画面 | 存档只序列化后端 GameContext，对话/立绘/选项在前端 store，读档后数据对不上画面 | 服务端 `_persist_blocked` 强制拒绝 + 前端按钮按 `canPersist` 置灰，只在脚本空闲时可存读档 |
| 读档后只剩 `——` 空屏 | 空文本区占位符（`TextFlow.vue`）+ 读档只 `deserialize` 数据，画面从未存过 | 存档增加 `dialogue` 段（DialogueRecorder 记录画面类消息），读档后前端 `restoreDialogue` 重放；`restoring` 标志让文本直接铺满不重播逐字 |

### 剧本 / DSL 类
| 坑 | 现象 | 解决 |
|---|---|---|
| `set_stat` 当增量用 | `data.set_stat("player","money",-30)` 把钱**设成** -30；`set_stat("reimu","relation",5)` 把好感从 20+ 覆写成 5 | 新增 `data.modify_stat(target, stat, delta)`（与 modify_relation 对称），修全部 4 处误用；DSL.txt 明确标注两者语义差异 |
| Python list 传给 Lua 是 userdata | `#ids` 报 "attempt to get length of a POBJECT value"，下标还是 0-based | 新 DSL 一律用 `runtime.table_from()` 返回真 Lua table；`data.list_characters()` 即此模式 |
| 剧本无法声明事件优先级 | 早晨问候与随机事件同挂 `on_day_begin`，执行顺序只能靠文件名 | 剧本返回表支持 `priority = "high"`，loader 映射到 EventPriority |
| 测试里重复 `loader.load_all()` | 每个剧本注册两次 → 早晨问候连弹两个选项 | env fixture 的 `init_engine` 已注册全部剧本，测试内不得重复 load；同时给 morning_call 加当天门控（`daily.last_morning_day`） |

### 剧本 / Hub 类
| 坑 | 现象 | 解决 |
|---|---|---|
| 好感度与关系阶段混在一起 | 好感满了就自动"恋爱"，剧情推进不受控 | 阶段独立为 `CharacterState.stage`，只由 `data.set_stage`（突破事件）改写；好感度可继续累积，阶段不变 |

| 坑 | 现象 | 解决 |
|---|---|---|
| `_send_hub` 在 `game.start` 时立即推 | Hub 角色列表为空 —— `reset_game` 还在 executor 里异步跑，角色尚未载入 | 改由序章播完的 `add_done_callback`（`event.done`）统一推送；前端 `enterHub()` 也会主动 `game.hub` 拉取 |
| 事件与对话混在一个剧本 | 早晨问候做成"每天必弹 + 强制选项"，玩家没有主动权 | 拆两类：自动事件（`on_day_begin`）vs 玩家主动对话（Hub 按钮 → `dialogue:<char>`） |
| 多角色早晨事件重复打扰 | 每个角色都注册 `on_day_begin`，一天被叫醒多次 | 共用当天占坑旗标 `daily.morning_done = day`，第一个成功触发的角色占位，其余跳过 |

### 文档 / 流程类
| 坑 | 现象 | 解决 |
|---|---|---|
| "37 指令"是笔误 | 实测 40（后加 minigame.start 变 41） | 文档全量修正，DSL.txt 一直是权威 |
| 多剧本干扰测试 | minigame_demo 无条件触发，卡住 coffee 测试的脚本线程 | 测试里显式设置 flag 阻止干扰剧本 |
| 自检剧本放进 `Data/scenarios` | 后端测试从 14s 变成超时（>2 分钟不结束） | 自检剧本含阻塞 `ask_choice`，且测试直接用真实剧本目录；改放 `tools/scenarios/`，用独立 `scripts_dir` 驱动 |
| e2e 脚本端口漂移 | 测试用 8799，dev.sh 用 8765 | 统一 8765（dev.sh 默认端口） |
| PowerShell heredoc 转义 | `cat <<'EOF'` 传参被 PowerShell 吃掉 | write_file（Windows 侧）+ cp 同步 WSL |

## 四、Git 留档版本

| 版本 | 说明 |
|---|---|
| **`pre-web-refactor`**（tag） | ⭐ **完整 v1 源码快照**（PySide6 桌面版，含全部代码/测试），重构后随时可回退查阅 |
| `b4db242` | 迁移 WSL 前完整快照（含未提交改动） |
| `ca2d29b` | 移除 PySide6 源码，转向前后端分离 |
| `bdb34ce` | 架构 v2 定稿 + backend/frontend 骨架 |
| `3a828d8` | **Phase 1**：后端引擎（沙箱/41 API/调度器/事件/状态/加载）+ WS 网关，88 测试 |
| `9c62de2` | **Phase 2**：Vue3+TS 最小前端 + day_advance 协议，89 测试 |
| `3ed2335` | **Phase 3**：存档系统 + 状态栏 + 存档界面 + 模式栈，102 测试 |
| `25acf53` | **Phase 4**：逐字打印/设置面板/音频 + 小游戏 Canvas 原型 |
| `f7094e9` | 小游戏模块化（注册表 + DSL minigame.start 阻塞触发）+ UI 模式栈修复 |
| `efe6e1e` → `f20dd05` | 交互打磨系列（共 12 提交）：小游戏协议 41 指令回写 / 逐字打印 deep watch 修复 / 段落点击推进(▼) / textIdle 门控 / autoAdvance 连续播放 / game.abort 释放线程 / 存档删除 / 立绘路径对齐 / stop.sh |

查看 v1 源码示例：
```bash
git show pre-web-refactor:Core/engine/script_runner.py
git show pre-web-refactor:tests/test_event_bus.py
```

## 五、当前已知未完成 / 待办

- **内容**：剧本数量少（4 个）、美术素材全空、音频素材全空
- **存档断线恢复**：记录意图未实现（体验优化，`docs/requirements.md` §5.6）
- **对话中途存档**：当前禁止（Lua 栈无法序列化），只能在事件边界存；已实现对话快照（`dialogue` 段）让读档还原画面，见 `docs/architecture.md` §4.6
- ~~日常事件在真实游玩中无法触发~~：已补工具条「下一天」按钮（`game.day_advance`），
  并新增每日早晨问候剧本；door 见 `docs/architecture.md`
- **挂起中重启的日志噪音**：`Future exception was never retrieved`，功能正常但应吞掉（见踩坑表）
- **前端自动化测试**：无（e2e-check.mjs 为手工联调脚本）
- **小游戏**：仅 1 个原型；肉鸽（杀戮尖塔式）未开始
- **设置面板**：音频音量已接（WebAudio），但无真实素材验证
- **性能预留**：小游戏 Canvas 独立层已验证（ADR-0005），大规模场景未压测

## 六、下一步建议

1. **内容创作**：扩充 Lua 剧本（日常事件、主线、好感度剧情）+ 补立绘/背景素材（按 `docs/archive/v1/美术资源规范.md`）
2. **小游戏生态**：以注册表 + `minigame.start` DSL 为基础，新增 1-2 个小游戏
3. **打磨**：文字特效（震动/渐变）、音频素材接入验证、断线恢复评估
