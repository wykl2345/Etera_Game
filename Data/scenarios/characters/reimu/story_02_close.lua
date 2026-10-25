-- 灵梦主线 2/4：扫不尽的落叶（好感 30 → 阶段「亲密」）
-- 突破条件：好感 ≥ 30 且已完成 1/4

return {
    on_event = "story:reimu_02",

    hub = {
        char = "reimu",
        label = "帮她扫落叶",
        order = 31,
        require_relation = 30,
        require_flag = "reimu.story_01_done",
        hide_flag = "reimu.story_02_done",
    },

    execute = function()
        data.log_start("reimu", "扫不尽的落叶")

        world.set_time("evening")
        ui.set_background("shrine", "fade")
        -- 突破事件用全屏 CG 特写：区别于普通对话（隐藏立绘，只留 CG 与文本）
        ui.cg("reimu_02_leaves")
        ui.show_character("reimu", "normal", "center")

        ui.text("傍晚的神社，落叶铺了一地。", "white")
        ui.text("灵梦拿着扫帚，扫到一半就停下来发呆。", "white")
        ui.text("灵梦：扫了还会落，落了我还得扫。有时候真不知道图什么。", "pink")

        local c = ui.ask_choice({
            "那就别扫了，我陪你坐着",
            "这是你的职责吧",
            "我帮你扫",
        })

        if c == 1 then
            ui.text("灵梦：……你今天倒是会说人话。", "pink")
            ui.text("她把扫帚一扔，在台阶上坐下。", "white")
            ui.text("灵梦：其实不是非得扫。只是不找点事做，就会想些没用的。", "pink")
            data.modify_relation("reimu", 12)
        elseif c == 2 then
            ui.text("灵梦：职责啊。说得真好听。", "pink")
            ui.text("灵梦：没人给钱，也没人记得。这算哪门子职责。", "red")
            data.modify_relation("reimu", 5)
        else
            ui.text("你接过扫帚。灵梦愣了一下，然后靠在柱子上看你扫。", "white")
            ui.text("灵梦：……喂，那边的角落还没扫到呢。", "pink")
            data.modify_relation("reimu", 9)
        end

        ui.text("", "white")
        ui.text("天色彻底暗下来。灵梦忽然开口，声音很轻。", "white")
        ui.text("灵梦：……有个人在旁边，好像确实不太一样。", "pink")
        ui.text("（与灵梦的关系：亲密）", "yellow")

        data.set_stage("reimu", "close")
        data.set_flag("reimu", "story_02_done", true)
        data.log_commit()
        ui.cg_off()
        ui.hide_character("reimu")
    end
}
