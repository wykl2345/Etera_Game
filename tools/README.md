# tools/ — 开发工具

不属于游戏内容的开发辅助脚本。

> **美术出图已改用 ChatGPT Plus**（2026-11），提示词见 `docs/美术提示词.md`。
> `comfyui_generate.py` / `process_assets.py` 是本地 ComfyUI 时期的遗留脚本，保留备查、不再作为主流程。
> 当前立绘后处理用 `process_sprite.py`（见下）。

## 立绘去背 / 规范化

`process_sprite.py` 把 ChatGPT 产出的立绘处理成引擎规格：

- **RGB / 全不透明**（常见白底或“棋盘格透明”被烘焙进图）→ rembg `isnet-anime` 去背
- **已有 alpha** → 跳过 rembg，只清低 alpha 噪点
- 统一缩放到 `1200×1800` RGBA，输出到 `resources/images/characters/{char}/{expr}.png`
- 比例不是 2:3 会直接拒绝，避免拉伸

```bash
.venv/bin/python tools/process_sprite.py \
  --char reimu --expr serious \
  --src incoming/art/characters/reimu/serious.png --force
```

首次运行会把 `isnet-anime` 模型（约 176MB）下载到 `.rembg-models/`（已 gitignore）。
验收与归档走 `docs/美术素材待办.md`。

## DSL 全指令自检

把覆盖全部 DSL 指令的剧本跑一遍，逐条断言返回值，输出 `[OK]/[NG]` 报告。**两种触发方式，跑的是同一个剧本、同一条事件**：

### 方式一：游戏内按钮（推荐）

Hub 系统栏 → **「自检」** 按钮。

前端先切到叙事界面，再发 `game.emit_event{event:"custom:run_selftest"}` → 后端 `bus.emit(...)` → 剧本响应。
（自检剧本会先弹选项，Hub 不渲染 ChoiceMenu，所以必须先切界面。）

对话进行中点击会提示「请先完成当前对话」（与存读档同一套 `canPersist` 判定），因为自检会连续输出大段文本，中途插入会打乱节奏。

点击后剧本先弹一个前置选择（灵梦问「怎么了，有事吗？」），选「帮我检查一下修行成果」才进入检查，选别的直接退出 —— 所以是在正常对话里主动进入，不是强行插入。

### 方式二：命令行（不需要浏览器）

```bash
.venv/bin/python tools/run_dsl_selftest.py
```

退出码 `0` = 全部通过；非 0 = 有失败项（明细直接打印）。用内存 output 驱动，不启动 WS/浏览器，适合改完 DSL 后快速回归。

## 剧本在哪、为什么这么挂

剧本：`Data/scenarios/system/dsl_selftest.lua`，监听 **`custom:run_selftest`**。

**不挂 `on_game_start`** —— 对话应由玩家主动触发，而不是开局强行插入。挂在自定义事件上后：

- 正常游玩完全不受影响（没人 emit 这个事件）
- 后端测试不受影响（测试只 emit 系统事件，不碰 `custom:run_selftest`）
- 想跑就跑，可重复触发（剧本自己会把改动的状态恢复原值）

> 上一版曾挂 `on_game_start`、放 `Data/scenarios/`，结果开局强制刷一屏检查输出，且让后端测试
> 从 14s 变成超时。改成自定义事件后两个问题都消失。

## 覆盖范围

52 条指令（不含 `minigame.*`）：

| 组 | 数量 | 指令 |
|---|---|---|
| `ui.*` | 13 | text / clear / show_image / hide_image / play_sound / stop_sound / play_music / stop_music / set_background / show_character / hide_character / ask_choice / ask_input |
| `data.*` | 15 | get_chara / **list_characters** / get_stat / set_stat / **modify_stat** / get_relation / set_relation / modify_relation / get_flag / set_flag / has_flag / get_inventory / add_item / remove_item / get_item_count |
| `world.*` | 6 | get_day / set_day / get_time / set_time / get_location / set_location |
| `event.*` | 3 | emit / listen / after_days |
| `util.*` | 5 | random / random_range / log / debug / sleep |

断言覆盖正常路径 + 边界：属性钳制（hp 上下限）、好感度钳制（±100）、`core` 命名空间拒写、`modify_stat` 增量语义、`list_characters` 返回真 Lua table（`#`/`ipairs`）、
`char:` 命名空间隔离、不存在角色/物品的返回约定、`random_range` 反序自动交换、`get_stat`
未知键走默认值等。

## 新增 DSL 指令时

1. 在 `Data/scenarios/system/dsl_selftest.lua` 对应段落加 `call(...)`（无返回值）或 `check(...)`（有返回值）
2. 跑 `run_dsl_selftest.py` 确认全绿
3. 同步更新 `DSL.txt` 与 `docs/progress.md`

## 已知偏差（剧本会打印，不判失败）

- `world.set_time` / `world.set_location` 不自动 emit `on_time_change` / `on_location_change`（事件名已预留，无触发点）
- `event.after_days` 为惰性占位，只写入 `temp`，不会真正延迟触发
