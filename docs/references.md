# Etera_Game 技术参考索引 (References)

> 目的：v1 源码已归档（tag `pre-web-refactor`），开发时以**官方文档为准**；本文档收录各依赖的官方文档链接与**版本坑位**，避免"缺代码示例 + 版本函数参数差异"导致的开发问题。
> 更新规则：每次升级依赖或踩到新坑，追加到对应章节。

---

## 一、环境版本基线（WSL Ubuntu-24.04 已确认）

| 组件 | 版本 | 说明 |
|---|---|---|
| Python | 3.12.3 | 系统自带，后端用 `.venv` |
| lupa | 2.8 | wheel 内置 Lua 5.1-5.5 + LuaJIT；**Mod 沙箱固定 `lupa.lua54`** |
| websockets (PyPI) | ≥ 14（建议最新 17.x） | 14.0 起新版 asyncio API 为默认 |
| Vue | 3.5.x | `npm create vite` 模板 `vue-ts` |
| Vite | 8.x | **要求 Node 20.19+ / 22.12+**；WSL 已装 **v24.19.0**（`~/.local/bin`） |
| Node (WSL) | v24.19.0 | 2026-08 安装，PATH 已写入 `~/.bashrc`；npm 11.17.0 |
| Pinia | 4.x | peer: `vue ^3.5.11` + `typescript >=5.6.0` |
| TypeScript | 5.9.3 | **必须锁 5.9.x**：TS 7 与 vue-tsc 3.x 不兼容（ERR_PACKAGE_PATH_NOT_EXPORTED，见 progress.md 踩坑）；官方推荐 <script setup lang="ts"> 写法 |

---

## 二、官方文档链接（均已验证可访问）

| 技术 | 文档首页 | API / 关键参考 |
|---|---|---|
| Python 3.12 asyncio | https://docs.python.org/3.12/library/asyncio.html | event loop: https://docs.python.org/3.12/library/asyncio-eventloop.html |
| lupa | https://github.com/scoder/lupa （无独立 readthedocs，README.rst 即文档） | coroutine 示例: https://github.com/scoder/lupa#lua-coroutines |
| websockets (Python) | https://websockets.readthedocs.io/ | API 参考: https://websockets.readthedocs.io/en/stable/reference/index.html |
| Vue 3 | https://vuejs.org/ | API: https://vuejs.org/api/ |
| Vite | https://vite.dev/ | 脚手架: `npm create vite@latest -- --template vue-ts` |
| Pinia | https://pinia.vuejs.org/ | API: https://pinia.vuejs.org/api/ |
| TypeScript | https://www.typescriptlang.org/ | Vue TS 指南: https://vuejs.org/guide/typescript/overview.html |
| Lua 5.4 手册 | https://www.lua.org/manual/5.4/ | 全版本入口: https://www.lua.org/manual/ |

---

## 三、版本坑位清单（开发必读）

### 1. asyncio（Python 3.12）
- `asyncio.get_event_loop()` **3.12 起弃用**（无当前事件循环时告警，未来将报错）。v1 代码 `event_bus.py` 就踩了此坑。
- 正确写法：协程内用 `asyncio.get_running_loop()`；入口用 `asyncio.run()`。
- 跨协程等待：`loop.create_future()` 创建 → `await future`。

### 2. websockets（Python）
- **14.0 起新版 asyncio 实现为默认**；旧实现移至 `websockets.legacy`，**17.0 移除 9.0 遗留的模块别名**。
- 新版导入：`from websockets.asyncio.server import serve` / `from websockets.asyncio.client import connect`。
- 回调签名：新版 `async def handler(websocket)` **单参数**；10.x 时代的 `(websocket, path)` 双参数已移除。
- 17.0：部分参数改 keyword-only（`send(text=...)`、`ping(ack_on_close=...)` 等）。

### 3. lupa（Lua 绑定）
- wheel 内置到 **Lua 5.5**，默认 `import lupa` 用最新版 → **Mod 沙箱必须固定 `import lupa.lua54`**，否则 Lua 版本随 lupa 升级漂移，Mod 手册（对应 5.4）与运行时不一致。
- Python 3.12 兼容：wheel 为 `cp39-abi3`（3.9+），官方支持 3.8+。
- 沙箱机制（官方）：`LuaRuntime(register_eval=False, register_builtins=False, attribute_filter=..., attribute_handlers=..., max_memory=...)`；移除标准库全局用 `lua.globals().os = None` 等。
- Lua 协程：`lua_func.coroutine(*args)` 包装后行为像 Python 生成器（`for x in gen` / `co.send(value)`），是调度器挂起/恢复的关键 API。

### 4. Vite / Node
- Vite 8 要求 **Node 20.19+ 或 22.12+**。
- WSL 已安装 Node **v24.19.0**（解压至 `~/.local/`，`export PATH="$HOME/.local/bin:$PATH"` 已写入 `~/.bashrc`）。升级/重装：下载官方 tarball `https://nodejs.org/dist/<version>/<version>-linux-x64.tar.xz` 解压到 `~/.local`。
- 注意：`latest-v2x.x` 目录随版本退役会被移除（v22 已 404），安装时用仍在维护的 LTS 线（如 `v24.x`）并写死具体版本号。

### 5. Vue / Pinia / TS
- `<script setup lang="ts">` 是官方推荐写法（create-vue 脚手架默认）。
- Pinia 4.x 需 `vue ^3.5.11` + `typescript >=5.6.0`，装包时注意版本匹配。
- 类型检查用 `vue-tsc`；VS Code 装 "Vue - Official" 扩展。

---

## 四、v1 源码参考（已归档，按需查阅）

完整源码与测试在 git tag `pre-web-refactor`，需要示例时：

```bash
git show pre-web-refactor:Core/engine/script_runner.py   # 调度器 v1 实现
git show pre-web-refactor:Core/engine/api_bridge.py      # API 白名单 v1 实现
git show pre-web-refactor:tests/test_event_bus.py        # 测试用例（重写时复用思路）
git show pre-web-refactor:tests/test_save_manager.py
```

> 注意：v1 基于 PySide6（Qt），其 `QEventLoop` 嵌套方案在 v2 由 asyncio 替代，参考时只看**逻辑与 API 语义**，不看 GUI 交互部分。
