-- 角色剧本：博丽灵梦 · 早晨叫醒（日常事件，非玩家主动触发）
-- 触发：on_day_begin，第 2 天起
-- 随机性：① 本角色当天有 50% 概率来叫你；② 多角色共用 daily.morning_done，
--         当天第一个成功触发的角色占坑，其余跳过 → 每天最多一次叫醒，且叫的人随机。
-- 时段重置由引擎负责（day_advance 时置为 morning），剧本不管时间规则。

return {
    on_event = "on_day_begin",
    priority = "high",

    execute = function()
        local day = world.get_day()
        if day < 2 then
            return
        end
        if data.get_flag("daily", "morning_done", 0) == day then
            return  -- 今天已经有人叫过了
        end
        if util.random() > 0.5 then
            return  -- 今天灵梦没来
        end

        data.set_flag("daily", "morning_done", day)

        ui.set_background("home", "fade")
        ui.text("―― " .. tostring(day) .. " 日目・朝 ――", "cyan", true)
        ui.show_character("reimu", "normal", "center")
        ui.text("灵梦：喂，起床了。太阳都晒屁股了。", "pink")

        local c = ui.ask_choice({ "起来了", "再睡五分钟", "装作没听见" })

        if c == 1 then
            ui.text("你翻身下床。灵梦满意地点了点头。", "white")
            data.modify_relation("reimu", 2)
        elseif c == 2 then
            ui.text("灵梦：……行吧，就五分钟。", "pink")
            data.modify_relation("reimu", 1)
        else
            ui.text("灵梦：喂！我听见你翻身了！", "red")
            data.modify_relation("reimu", -1)
        end

        ui.hide_character("reimu")
    end
}
