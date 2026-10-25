# tools/ — 开发工具

不属于游戏内容的开发辅助脚本，**不会被引擎自动加载**。

## DSL 全指令自检

把一个覆盖全部 DSL 指令的剧本跑一遍，逐条断言返回值，输出 `[OK]/[NG]` 报告。

```bash
# 在项目根执行
.venv/bin/python tools/run_dsl_selftest.py
```

退出码 `0` = 全部通过；非 0 = 有失败项（明细直接打印）。

### 它做什么

- 用 `init_engine(output=...)` 组装完整引擎，`output` 换成内存收集器（**不启动 WS、不需要浏览器**）
- 驱动 `tools/scenarios/dsl_selftest.lua`：脚本在独立线程执行，阻塞指令（`ask_choice`/`ask_input`）由主线程自动应答
- 收集所有 `ui.*` 消息并打印，最后汇总 `[OK]/[NG]` 计数
- 核对剧本执行后游戏状态是否恢复到起始值（防止自检污染存档）

### 当前覆盖

40 条指令（不含 `minigame.*`）：

| 组 | 数量 | 指令 |
|---|---|---|
| `ui.*` | 13 | text / clear / show_image / hide_image / play_sound / stop_sound / play_music / stop_music / set_background / show_character / hide_character / ask_choice / ask_input |
| `data.*` | 13 | get_chara / get_stat / set_stat / get_relation / set_relation / modify_relation / get_flag / set_flag / has_flag / get_inventory / add_item / remove_item / get_item_count |
| `world.*` | 6 | get_day / set_day / get_time / set_time / get_location / set_location |
| `event.*` | 3 | emit / listen / after_days |
| `util.*` | 5 | random / random_range / log / debug / sleep |

断言覆盖正常路径 + 边界：属性钳制（hp 上限/下限）、好感度钳制（±100）、`core` 命名空间拒写、`char:` 命名空间隔离、不存在角色/物品的返回约定、`random_range` 反序自动交换等。

### 为什么放在这里而不是 Data/scenarios/

`Data/scenarios/` 下的剧本会被引擎全量注册，而 `backend/tests/` 的端到端测试直接用真实目录（`test_loader_registers_all_three` 断言只加载 3 个正式剧本）。

自检剧本含阻塞的 `ask_choice`/`ask_input`，一旦放进 `Data/scenarios/`：

- 后端测试会超时（实测 14s → 超 2 分钟）
- 正常游玩每次新游戏都会被刷一屏检查输出

所以它固定放在 `tools/scenarios/`，`run_dsl_selftest.py` 把 `scripts_dir` 指向该目录，与正式剧本完全隔离。

### 想在实际游戏里看效果

临时拷进去即可（记得跑完删掉，否则干扰测试）：

```bash
cp tools/scenarios/dsl_selftest.lua Data/scenarios/system/
# 玩完清理
rm Data/scenarios/system/dsl_selftest.lua
```

### 新增 DSL 指令时

1. 在 `tools/scenarios/dsl_selftest.lua` 对应段落加 `call(...)`（无返回值）或 `check(...)`（有返回值）
2. 跑 `run_dsl_selftest.py` 确认全绿
3. 同步更新 `DSL.txt` 与 `docs/progress.md`

### 已知偏差（剧本会打印，不判失败）

- `world.set_time` / `world.set_location` 不自动 emit `on_time_change` / `on_location_change`（事件名已预留，无触发点）
- `event.after_days` 为惰性占位，只写入 `temp`，不会真正延迟触发
