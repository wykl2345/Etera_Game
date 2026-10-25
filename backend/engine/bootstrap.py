"""引擎初始化（bootstrap）—— 组装全部核心模块（对齐 v1 bootstrap 职责）。

流程：角色加载 → 沙箱构建 → API 注入 → 剧本注册。
返回 EngineBundle 供测试与 ws_gateway/main 共用。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from engine.api_bridge import LuaAPI
from engine.character_model import CharacterModel
from engine.event_bus import EventBus
from engine.game_context import GameContext, StatBlock
from engine.loader import ScenarioLoader
from engine.sandbox import LuaSandbox
from engine.script_runner import ScriptScheduler, UIOutput

logger = logging.getLogger(__name__)


@dataclass
class EngineBundle:
    bus: EventBus
    ctx: GameContext
    sandbox: LuaSandbox
    scheduler: ScriptScheduler
    api: LuaAPI
    output: UIOutput
    character_model: CharacterModel
    save_manager: Any = None


def _apply_characters(ctx: GameContext, cm: CharacterModel) -> None:
    for template in cm.load_all().values():
        data = cm.apply_template(template)
        ch = ctx.add_character(data["id"], data["name"])
        ch.stats = StatBlock.from_dict(data["stats"])
        ch.relation = data["relation"]
        ch.location = data["location"]
        for key, value in data["flags"].items():
            ctx.set_character_flag(data["id"], key, value)


def reset_game(bundle: "EngineBundle") -> None:
    """开始新游戏：重置全部状态 + 重载角色 + 解除中止标志。

    单连接可能多次 game.start，必须重置否则 flag 残留导致剧本不再触发。
    """
    bundle.scheduler.stop_all()  # 中止上一局残留的挂起脚本（若有）
    bundle.ctx.reset()
    _apply_characters(bundle.ctx, bundle.character_model)
    bundle.scheduler.reset_abort()
    logger.info("新游戏：状态已重置")


def init_engine(
    output: UIOutput,
    scripts_dir: Any = "data/scenarios",
    characters_dir: Any = "data/characters",
    saves_dir: Any = "saves",
    debug_mode: bool = False,
) -> EngineBundle:
    """构建完整引擎（不含 WS/网络，output 由调用方注入）。"""
    bus = EventBus()
    ctx = GameContext()
    cm = CharacterModel(Path(characters_dir))
    _apply_characters(ctx, cm)
    logger.info("角色已加载: %s", list(ctx.get_all_characters().keys()))

    sandbox = LuaSandbox()
    scheduler = ScriptScheduler(bus, sandbox, ctx, output, scripts_dir=Path(scripts_dir))
    api = LuaAPI(scheduler, ctx, bus, debug_mode=debug_mode, sandbox=sandbox)
    sandbox.inject_api(api.build_env())

    loader = ScenarioLoader(sandbox, bus, Path(scripts_dir))
    loaded = loader.load_all()
    logger.info("剧本已注册: %s", loaded)

    from engine.save_manager import SaveManager

    save_manager = SaveManager(bus, ctx, base_dir=Path(saves_dir))

    return EngineBundle(
        bus=bus, ctx=ctx, sandbox=sandbox,
        scheduler=scheduler, api=api, output=output,
        character_model=cm, save_manager=save_manager,
    )
