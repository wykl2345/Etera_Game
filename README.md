# Etera_Game (EE1)

Emuera/ERA 风格叙事文字冒险游戏引擎，前后端分离架构。

- **后端**: Python 3.12 + asyncio（Lua 沙箱 + 事件总线 + 状态管理）
- **前端**: Vue 3 + Vite + TypeScript（浏览器渲染）
- **通信**: WebSocket (JSON)，40 个 Lua 指令为 Mod 契约（DSL.txt）
- **开发环境**: WSL Ubuntu-24.04，项目位于 `~/projects/EE1`（以 WSL 内为准）

## 文档体系（agent 开发的事实来源）

| 文档 | 内容 |
|---|---|
| `CONTEXT.md` | 领域词汇表（Event/Scenario/Scene、叙事/系统界面等统一语言） |
| `docs/architecture.md` | 架构设计 + WS 通信协议（requestId 机制、asyncio 调度） |
| `docs/requirements.md` | ★ 正式 PRD：Phase 1-2 需求条目 + 验收标准（开发按此逐条实现） |
| `docs/references.md` | 官方文档链接 + 版本坑位 + v1 源码查阅方法 |
| `docs/adr/` | 决策记录 0001-0006 |
| `DSL.txt` | Mod 契约：40 个 Lua 指令（协议基准，不得变更语义） |
| `docs/archive/v1/` | v1 文档归档（含 UI 模式栈 PRD；完整源码见 git tag `pre-web-refactor`） |

> 规则：开发长任务以文档驱动——先读 `requirements.md` 对应条目，再实现；新决策写入 `docs/adr/`，新术语写入 `CONTEXT.md`，新坑位写入 `references.md`。

## 环境速查

```bash
# 项目位置（WSL）
cd ~/projects/EE1

# 后端（Python 3.12 + .venv）
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
.venv/bin/python -m pytest          # 测试（Phase 1 后可用）

# 前端（Node ≥24，已装于 ~/.local）
cd frontend && npm install && npm run dev   # Phase 2 后可用
```

## 迁移状态

- ✅ 环境迁移 WSL（Ubuntu 24.04.1，系统已更新）
- ✅ 文档体系 v2 定稿（架构/PRD/参考/ADR/词汇表）
- ✅ **Phase 1 后端引擎完成**：沙箱(lupa54)/API 白名单(40)/调度器/事件总线/状态/剧本加载 + WS 网关，88 测试全绿（commit 3a828d8）
- ✅ **Phase 2 最小前端完成**：Vue3+TS（主菜单/文本流/选项/立绘背景/输入），3 剧本全跑 + 日常事件循环，联调验收通过（commit 9c62de2）
- ✅ **Phase 3 完成**：存档系统（迁移链/备份/20 槽）+ 状态栏（status.sync）+ 存档界面 + UI 模式栈（commit 3ed2335）
- ✅ **Phase 4 完成**：逐字打印 + 设置面板 + WebAudio 音频 + 小游戏 Canvas 原型（史莱姆回合制，commit 25acf53）
- 🎯 路线图 4 个 Phase 全部完成，进入内容创作阶段（Lua 剧本 / 美术素材）

