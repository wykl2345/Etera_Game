# Etera_Game 开发进度记录

> 更新: 2026-08-18 | 状态: 引擎平台完成（Phase 1-4 全达成），进入内容创作阶段

---

## 一、项目概览

Etera_Game 前后端分离重构：Python 引擎核心（Lua 沙箱 + 事件总线 + 状态 + 存档）经 WebSocket 对接 Vue 3 前端（浏览器渲染）。Emuera/ERA 风格叙事文字冒险游戏。

```
✅ Phase 1 后端引擎     ✅ Phase 2 最小前端     ✅ Phase 3 存档/状态栏     ✅ Phase 4 打磨/小游戏
✅ 后端 107 测试全绿    ✅ 前端 type-check + build    ✅ 联调验收（dev.sh 一键启动）
```

## 二、完成度评估

| 模块 | 完成度 | 说明 |
|---|---|---|
| 后端引擎核心 | **95%** | Lua 沙箱（lupa54 + 安全限制 + Mock 降级）、41 指令 API 白名单、线程池调度器（Future 挂起/恢复）、事件总线、分层状态（core 保护）、剧本加载、GameContext 序列化 |
| 后端存档系统 | **90%** | 版本化 JSON（2.0.0）+ 迁移链（1.0→2.0）+ 原子写入 + 备份 + 20 槽 + 快速存档；断线恢复未做（记录意图） |
| WS 网关/协议 | **90%** | 单连接单会话、queue 串行发送、requestId 机制、status.sync 推送、存档/小游戏消息；无断线重连 |
| 前端叙事界面 | **85%** | 文本流（逐字打印 + 段落点击推进 + 快进）、选项、立绘/背景占位、输入、小游戏触发 |
| 前端系统界面 | **80%** | 主菜单（Web 现代化）、状态栏（HP/MP/体力条）、存档界面（槽位/删除/拖拽）、设置面板（localStorage） |
| 小游戏 | **60%** | Canvas 独立层架构验证（注册表 + MinigameHost + 结果回传）；仅 1 个原型（史莱姆回合制） |
| 内容资产 | **10%** | 4 个 Lua 剧本（v1 的 3 个 + 演示 1 个）；美术/音频素材全空（占位显示） |
| 测试 | **85%** | 后端 107 项（事件/状态/调度/存档/WS 端到端）；前端无自动化测试（e2e-check.mjs 手工联调脚本） |
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
| Lua 版本漂移风险 | lupa wheel 内置到 5.5，默认导入跟随升级 | ADR-0004：固定 `import lupa.lua54` |

### 后端 / asyncio 类
| 坑 | 现象 | 解决 |
|---|---|---|
| `asyncio.get_event_loop()` 3.12 弃用 | DeprecationWarning（v1 event_bus 遗留） | v2 用 `get_running_loop()` / `loop.create_future()` |
| websockets 14+ API 变更 | 旧 `(ws, path)` 回调移除、新 asyncio 命名空间 | `from websockets.asyncio.server import serve`，单参数回调 |
| WS 网关 `game.start` await 死锁 | `asyncio.to_thread` 阻塞消息循环，收不到 choice.made | 改为 fire-and-forget 提交 executor（不 await） |
| 单 worker executor 被挂起脚本占用 | 回主菜单后再次 game.start 排队永不执行 → 空对话 | `game.abort` 消息：stop_all 中止挂起脚本释放线程 |
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

### 文档 / 流程类
| 坑 | 现象 | 解决 |
|---|---|---|
| "37 指令"是笔误 | 实测 40（后加 minigame.start 变 41） | 文档全量修正，DSL.txt 一直是权威 |
| 多剧本干扰测试 | minigame_demo 无条件触发，卡住 coffee 测试的脚本线程 | 测试里显式设置 flag 阻止干扰剧本 |
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
| `9e7345e` | （最新）段落点击推进系列修复收尾 |

查看 v1 源码示例：
```bash
git show pre-web-refactor:Core/engine/script_runner.py
git show pre-web-refactor:tests/test_event_bus.py
```

## 五、当前已知未完成 / 待办

- **内容**：剧本数量少（4 个）、美术素材全空、音频素材全空
- **存档断线恢复**：记录意图未实现（体验优化，`docs/requirements.md` §5.6）
- **前端自动化测试**：无（e2e-check.mjs 为手工联调脚本）
- **小游戏**：仅 1 个原型；肉鸽（杀戮尖塔式）未开始
- **设置面板**：音频音量已接（WebAudio），但无真实素材验证
- **性能预留**：小游戏 Canvas 独立层已验证（ADR-0005），大规模场景未压测

## 六、下一步建议

1. **内容创作**：扩充 Lua 剧本（日常事件、主线、好感度剧情）+ 补立绘/背景素材（按 `docs/archive/v1/美术资源规范.md`）
2. **小游戏生态**：以注册表 + `minigame.start` DSL 为基础，新增 1-2 个小游戏
3. **打磨**：文字特效（震动/渐变）、音频素材接入验证、断线恢复评估
