-- 日常事件：早晨的呼唤
-- 触发：on_day_begin（每天），第 2 天起（第 1 天是序章当天）
-- 设计：每天必有角色来叫醒玩家，随机挑谁 —— 不写死角色 ID，用
--       data.list_characters() 取已加载角色，所以新增角色后自动参与。
-- 作用：① 把时段重置为早晨；② 提供每日好感成长途径，
--       让 coffee_shop（需好感≥20）这类事件能随天数自然解锁。

return {
    on_event = "on_day_begin",
    -- 优先级 high：早晨问候排在其它日常事件之前（同事件多剧本时生效）
    priority = "high",

    execute = function()
        local day = world.get_day()
        -- 第 1 天是序章当天，从第 2 天开始
        if day < 2 then
            return
        end

        -- 同一天只播一次：防止重复注册或一天内多次 emit on_day_begin 时重复打扰
        if data.get_flag("daily", "last_morning_day", 0) == day then
            return
        end

        -- 随机挑一个已加载的角色（不硬编码 ID）
        local ids = data.list_characters()
        if #ids == 0 then
            return
        end
        local who = ids[util.random_range(1, #ids)]
        local info = data.get_chara(who)
        if not info then
            return
        end
        local name = tostring(info.name)

        -- 新的一天从早晨开始
        world.set_time("morning")

        ui.set_background("home", "fade")
        ui.text("―― " .. tostring(day) .. " 日目・朝 ――", "cyan", true)
        ui.show_character(who, "normal", "center")
        ui.text(name .. "：喂——起床了，太阳都晒屁股了。", "pink")

        local c = ui.ask_choice({ "起来了", "再睡五分钟", "装作没听见" })

        if c == 1 then
            ui.text("你翻身下床，今天看起来会是个好日子。", "white")
            data.modify_relation(who, 2)
            util.log("[早晨] " .. name .. " 叫醒，好感 +2")
        elseif c == 2 then
            ui.text(name .. "：……行吧，就五分钟。", "pink")
            data.modify_relation(who, 1)
            util.log("[早晨] " .. name .. " 叫醒，好感 +1")
        else
            ui.text(name .. "：喂！我知道你听见了！", "red")
            data.modify_relation(who, -1)
            util.log("[早晨] " .. name .. " 叫醒，好感 -1")
        end

        ui.hide_character(who)
        data.set_flag("daily", "last_morning_day", day)
    end
}
