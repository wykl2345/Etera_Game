-- 角色剧本：雾雨魔理沙 · 日常闲聊
-- Hub 入口：主界面选中魔理沙 → 「聊聊」

return {
    on_event = "dialogue:marisa",

    hub = {
        char = "marisa",
        label = "聊聊",
        order = 10,
        daily_limit = 3,
    },

    execute = function()
        data.log_start("marisa", "闲聊")
        local rel = data.get_relation("marisa")

        ui.set_background("forest", "fade")
        ui.show_character("marisa", "grin", "center")

        if rel >= 30 then
            ui.text("魔理沙：来得正好！刚调了瓶新东西，试试？", "pink")
        elseif rel >= 10 then
            ui.text("魔理沙：哟，稀客。", "pink")
        else
            ui.text("魔理沙：……你谁啊？", "pink")
        end

        local c = ui.ask_choice({ "聊聊魔法", "看她搜集的破烂", "告辞" })

        if c == 1 then
            ui.text("魔理沙兴致勃勃地讲了半小时魔法理论。", "white")
            ui.text("（好感 +1）", "gray")
            data.modify_relation("marisa", 1)
        elseif c == 2 then
            ui.text("一堆看不懂的魔法道具，还有几本借来没还的书。", "white")
            ui.text("（好感 +2，捡到 1 个发光蘑菇）", "gray")
            data.modify_relation("marisa", 2)
            data.add_item("glowing_mushroom", 1)
        else
            ui.text("魔理沙：哎，这就走啦？", "pink")
        end

        ui.hide_character("marisa")
        data.log_commit()
    end
}
