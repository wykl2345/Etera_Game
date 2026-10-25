-- 日常事件：咖啡店
-- 对应设计文档中的示例脚本
-- 仅在触发条件满足时执行

return {
    on_event = "on_day_begin",

    execute = function()
        -- 只在第5天之后触发
        if world.get_day() < 5 then
            return
        end

        -- 再检查灵梦的好感度
        local reimu = data.get_chara("reimu")
        if not reimu then
            return
        end
        -- 触发门槛：好感 ≥ 6。
        -- 原先写 20，但玩家初始好感 0、每日早晨问候只 +2 且随机给某个角色，
        -- 实际要玩二十来天才能解锁 —— 调低到 6 让它在第 5 天前后自然出现。
        -- 想调整难度改这个数即可（纯内容参数）。
        if reimu.relation < 6 then
            return
        end

        -- 检查是否已经触发过
        if data.get_flag("coffee_mod", "met_at_cafe", false) then
            return
        end

        -- 触发事件
        ui.show_image("reimu_normal", "right")
        ui.text("灵梦在咖啡店门口等着你。", "white")
        ui.text("她看起来像是在等人。")

        local choice = ui.ask_choice({"进去打招呼", "假装没看见"})

        if choice == 1 then
            ui.text("灵梦：来得正好，帮我付咖啡钱。", "pink")
            -- 注意：扣钱/加好感都要用增量 API，
            -- set_stat 是设绝对值（曾经误用导致把好感从 20 覆写成 5）
            data.modify_stat("player", "money", -30)
            data.modify_relation("reimu", 5)
            data.set_flag("coffee_mod", "met_at_cafe", true)
            ui.text("（灵梦的好感度上升了！）", "yellow")
            ui.text("（花了30元钱。）", "gray")
        else
            ui.text("你假装没看见，快步走过。", "gray")
            ui.text("灵梦似乎没有注意到你。", "gray")
        end

        ui.hide_image("reimu_normal")
    end
}
