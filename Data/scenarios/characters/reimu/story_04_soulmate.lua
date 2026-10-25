-- 灵梦主线 4/4：日出（好感 80 → 阶段「伴侣」）
-- 突破条件：好感 ≥ 80 且已完成 3/4

return {
    on_event = "story:reimu_04",

    hub = {
        char = "reimu",
        label = "一起看日出",
        order = 33,
        require_relation = 80,
        require_flag = "reimu.story_03_done",
        hide_flag = "reimu.story_04_done",
    },

    execute = function()
        data.log_start("reimu", "日出")

        world.set_time("dawn")
        ui.set_background("shrine", "fade")
        -- 突破事件用全屏 CG 特写：区别于普通对话（隐藏立绘，只留 CG 与文本）
        ui.cg("reimu_04_sunrise")
        ui.show_character("reimu", "happy", "center")

        ui.text("天还没亮，你就被灵梦从被窝里拽了起来。", "white")
        ui.text("灵梦：快点，晚了就看不到了。", "pink")
        ui.text("山顶的风很冷。东边的天空正在一点点发白。", "white")

        local c = ui.ask_choice({
            "以后每天都一起看",
            "这样就够了",
            "……好冷",
        })

        if c == 3 then
            ui.text("灵梦：真是的。", "pink")
            ui.text("她把自己的披肩扔到你肩上，然后靠了过来。", "white")
            data.modify_relation("reimu", 12)
        elseif c == 1 then
            ui.text("灵梦：每天？你可真敢说。", "pink")
            ui.text("灵梦：……不过，反正我也每天都会在这里。", "pink")
            data.modify_relation("reimu", 15)
        else
            ui.text("灵梦：嗯。", "pink")
            ui.text("她没有多说，只是把手放在你手边，没有挪开。", "white")
            data.modify_relation("reimu", 13)
        end

        ui.text("", "white")
        ui.text("太阳从山脊后面升起来，把整座神社染成暖色。", "white")
        ui.text("灵梦：……以后这里，也是你的地方了。", "pink")
        ui.text("（与灵梦的关系：伴侣）", "yellow")

        data.set_stage("reimu", "soulmate")
        data.set_flag("reimu", "story_04_done", true)
        -- 首次突破伴侣时给一份纪念品
        data.add_item("博丽神社的御守", 1)
        data.log_commit()
        ui.cg_off()
        ui.hide_character("reimu")
    end
}
