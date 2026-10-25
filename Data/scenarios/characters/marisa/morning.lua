-- 角色剧本：雾雨魔理沙 · 早晨叫醒（日常事件，非玩家主动触发）
-- 触发：on_day_begin，第 2 天起，本角色当天 50% 概率
-- 与灵梦的 morning.lua 共用 daily.morning_done：当天谁先触发就谁叫，其余跳过。

return {
    on_event = "on_day_begin",
    priority = "high",

    execute = function()
        data.log_start("marisa", "清晨叫醒")
        local day = world.get_day()
        if day < 2 then
            return
        end
        if data.get_flag("daily", "morning_done", 0) == day then
            return  -- 今天已经有人叫过了
        end
        if util.random() > 0.5 then
            return  -- 今天魔理沙没来
        end

        data.set_flag("daily", "morning_done", day)

        ui.set_background("home", "fade")
        ui.text("―― " .. tostring(day) .. " 日目・朝 ――", "cyan", true)
        ui.show_character("marisa", "grin", "center")
        ui.text("魔理沙：起床啦！今天天气好得不得了！", "pink")

        local c = ui.ask_choice({ "起来了", "再睡五分钟", "装作没听见" })

        if c == 1 then
            ui.text("你翻身下床。魔理沙已经把窗户全打开了。", "white")
            data.modify_relation("marisa", 2)
        elseif c == 2 then
            ui.text("魔理沙：五分钟？那可说好了啊。", "pink")
            data.modify_relation("marisa", 1)
        else
            ui.text("魔理沙：喂——！别装睡！", "red")
            data.modify_relation("marisa", -1)
        end

        ui.hide_character("marisa")
        data.log_commit()
    end
}
