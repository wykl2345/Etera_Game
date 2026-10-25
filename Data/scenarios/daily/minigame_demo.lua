-- 演示剧本：剧本内触发小游戏（DSL minigame.start）
-- 触发: custom:run_minigame_demo（主动触发，不挂 on_day_begin）
--       原因：小游戏会打断日常流程，不该每天点「下一天」就弹出来。
--       触发方式：game.emit_event{event="custom:run_minigame_demo"}
-- 展示: minigame.start 阻塞 API → 结果回传 → 分支处理

return {
    on_event = "custom:run_minigame_demo",

    execute = function()
        if data.get_flag("demo", "minigame_done", false) then
            ui.text("（这场战斗已经打过了，演示到此为止）", "gray")
            return
        end

        ui.text("一只史莱姆挡住了去路！", "yellow")
        ui.show_image("slime", "center")

        -- 触发小游戏（脚本挂起，等玩家游玩结束）
        local result = minigame.start("slime_battle", { hp = 30 })

        if result.won then
            ui.text("你击败了史莱姆，获得了奖励！", "yellow")
            data.modify_stat("player", "money", result.score or 10)
            data.modify_relation("marisa", 2)
        else
            ui.text("你被史莱姆击败了，灰溜溜地逃走了……", "red")
        end

        data.set_flag("demo", "minigame_done", true)
    end
}
