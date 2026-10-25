-- 灵梦主线 1/4：神社的午后（好感 10 → 阶段「友人」）
-- 突破条件：好感 ≥ 10；完成后按钮隐藏（hide_flag）
-- 关系突破必须走事件：好感度满了也不会自动升阶

return {
    on_event = "story:reimu_01",

    hub = {
        char = "reimu",
        label = "去神社看看",
        order = 30,
        require_relation = 10,
        hide_flag = "reimu.story_01_done",
    },

    execute = function()
        data.log_start("reimu", "神社的午后")

        ui.set_background("shrine", "fade")
        -- 突破事件用全屏 CG 特写：区别于普通对话（隐藏立绘，只留 CG 与文本）
        ui.cg("reimu_01_afternoon")
        ui.show_character("reimu", "normal", "center")

        ui.text("午后的博丽神社，安静得能听见风铃。", "white")
        ui.text("灵梦坐在缘侧，手里捧着茶，一副刚睡醒的样子。", "white")
        ui.text("灵梦：……又是你啊。最近来得挺勤的。", "pink")

        local c = ui.ask_choice({
            "因为这里很舒服",
            "因为想见你",
            "路过而已",
        })

        if c == 1 then
            ui.text("灵梦：舒服？这破神社除了没人来，确实挺舒服的。", "pink")
            ui.text("她笑了一下，把茶往你这边推了推。", "white")
            data.modify_relation("reimu", 8)
        elseif c == 2 then
            ui.text("灵梦：……哈？", "pink")
            ui.text("她愣了一下，然后把脸埋进茶碗后面。", "white")
            ui.text("灵梦：说这种话，茶可不会多给你一杯。", "pink")
            data.modify_relation("reimu", 12)
        else
            ui.text("灵梦：路过能路过到山顶上来？你可真闲。", "pink")
            data.modify_relation("reimu", 3)
        end

        ui.text("", "white")
        ui.text("灵梦：……算了，坐吧。反正也没别人来。", "pink")
        ui.text("她说这话的时候，语气比平时松了一些。", "white")

        -- 关系突破：好感度不是唯一条件，必须由这个事件推进阶段
        data.set_stage("reimu", "friendly")
        data.set_flag("reimu", "story_01_done", true)
        ui.text("（与灵梦的关系：友人）", "yellow")

        data.log_commit()
        ui.cg_off()
        ui.hide_character("reimu")
    end
}
