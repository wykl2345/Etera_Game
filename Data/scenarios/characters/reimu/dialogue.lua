-- 角色剧本：博丽灵梦 · 日常闲聊
-- Hub 入口：主界面选中灵梦 → 「聊聊」
-- 组织约定：一个角色的多个剧本放在 characters/<角色ID>/ 下，各自声明自己的 Hub 按钮
--          与监听事件，方便单独修改和测试。

return {
    on_event = "dialogue:reimu",

    hub = {
        char = "reimu",
        label = "聊聊",
        order = 10,
    },

    execute = function()
        data.log_start("reimu", "闲聊")
        local rel = data.get_relation("reimu")

        ui.set_background("shrine", "fade")
        ui.show_character("reimu", "normal", "center")

        -- 好感不同，开场也不同（剧本内按数值分支）
        if rel >= 30 then
            ui.text("灵梦：又是你啊。……茶还是老样子？", "pink")
        elseif rel >= 10 then
            ui.text("灵梦：哦，来了。坐吧。", "pink")
        else
            ui.text("灵梦：……有事？", "pink")
        end

        local c = ui.ask_choice({ "随便聊聊", "帮忙做事", "告辞" })

        if c == 1 then
            ui.text("你们聊了些幻想乡的琐事。", "white")
            data.modify_relation("reimu", 1)
        elseif c == 2 then
            ui.text("你帮灵梦整理了神社的赛钱箱。", "white")
            ui.text("（好感 +3，体力 -5）", "gray")
            data.modify_relation("reimu", 3)
            data.modify_stat("player", "stamina", -5)
        else
            ui.text("灵梦：嗯，慢走。", "pink")
        end

        ui.hide_character("reimu")
        data.log_commit()
    end
}
