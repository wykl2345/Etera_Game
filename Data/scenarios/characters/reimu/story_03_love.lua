-- 灵梦主线 3/4：神社的台阶（好感 60 → 阶段「恋爱」）
-- 突破条件：好感 ≥ 60 且已完成 2/4

return {
    on_event = "story:reimu_03",

    hub = {
        char = "reimu",
        label = "夜里去神社",
        order = 32,
        require_relation = 60,
        require_flag = "reimu.story_02_done",
        hide_flag = "reimu.story_03_done",
    },

    execute = function()
        data.log_start("reimu", "神社的台阶")

        world.set_time("night")
        ui.set_background("shrine", "fade")
        ui.show_character("reimu", "normal", "center")

        ui.text("夜里的神社，只有灯笼还亮着。", "white")
        ui.text("灵梦坐在台阶上，没有像白天那样懒散，反而很安静。", "white")
        ui.text("灵梦：这么晚还上来，你是不是有点不正常。", "pink")

        local c = ui.ask_choice({
            "我有话想说",
            "就是想见你",
            "睡不着，随便走走",
        })

        if c == 3 then
            ui.text("灵梦：……行吧，那我也随便坐坐。", "pink")
            ui.text("你们沉默地坐了一会儿。有些话，好像不用说出口。", "white")
            data.modify_relation("reimu", 10)
        else
            if c == 1 then
                ui.text("你说了。说得很慢，也很直白。", "white")
            else
                ui.text("你说想见她。就这么简单。", "white")
            end
            ui.text("", "white")
            ui.text("灵梦很久没有说话。久到你开始后悔。", "white")
            ui.text("灵梦：……我一直觉得，这种事离我很远。", "pink")
            ui.text("灵梦：巫女嘛。守着神社，看着四季，一个人也挺好。", "pink")
            ui.text("她转过头来，眼睛在灯笼下亮得有点晃。", "white")
            ui.text("灵梦：可你偏偏老是来。", "pink")
            ui.text("灵梦：……那我要开始习惯有人陪了。你负责。", "pink")
            data.modify_relation("reimu", 18)
        end

        ui.text("", "white")
        ui.text("（与灵梦的关系：恋爱）", "yellow")

        data.set_stage("reimu", "love")
        data.set_flag("reimu", "story_03_done", true)
        data.log_commit()
        ui.hide_character("reimu")
    end
}
