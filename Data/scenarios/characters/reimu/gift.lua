-- 角色剧本：博丽灵梦 · 送礼物（演示金币交易 + 背包）
-- Hub 入口：选中灵梦 → 「带点东西去」
-- 用 data.buy_item 走交易系统：钱不够会买不到（不会扣款）

return {
    on_event = "action:reimu_gift",

    hub = {
        char = "reimu",
        label = "带点东西去",
        order = 25,
        daily_limit = 1,
    },

    execute = function()
        data.log_start("reimu", "带点东西去")

        ui.set_background("shrine", "fade")
        ui.show_character("reimu", "normal", "center")

        local money = data.get_player_stat("player", "money")
        ui.text("灵梦：嗯？手里拿的什么。", "pink")

        if money < 30 then
            ui.text("你摸了摸口袋 —— 空的。", "gray")
            ui.text("灵梦：……看你那表情，算了，我请你喝茶吧。", "pink")
            data.modify_relation("reimu", 1)
            data.log_commit()
            ui.hide_character("reimu")
            return
        end

        local c = ui.ask_choice({
            "煎茶（30 文）",
            "团子（50 文）",
            "什么也没带",
        })

        if c == 3 then
            ui.text("灵梦：那你还摆出那副样子。", "pink")
            data.modify_relation("reimu", -1)
        elseif c == 1 then
            -- 交易：钱够才成功；成功会自动扣款 + 入包
            if data.buy_item("煎茶", 30, 1) then
                data.remove_item("煎茶", 1)   -- 当场送出
                ui.text("你把煎茶递过去。灵梦接过来闻了闻。", "white")
                ui.text("灵梦：……还算你有心。", "pink")
                data.modify_relation("reimu", 5)
            else
                ui.text("（钱不够，买不成）", "gray")
            end
        else
            if data.buy_item("团子", 50, 1) then
                data.remove_item("团子", 1)
                ui.text("灵梦看着团子，眼睛亮了一下。", "white")
                ui.text("灵梦：……这个，我很喜欢。", "pink")
                data.modify_relation("reimu", 8)
            else
                ui.text("（钱不够，买不成）", "gray")
            end
        end

        data.log_commit()
        ui.hide_character("reimu")
    end
}
