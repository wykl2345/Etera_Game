-- 系统剧本：DSL 全指令自检
-- 主题：博丽神社·修行成果检验
--
-- 覆盖范围（40 个，不含 minigame.*）：
--   ui.*     13  text/clear/show_image/hide_image/play_sound/stop_sound
--                play_music/stop_music/set_background/show_character
--                hide_character/ask_choice/ask_input
--   data.*   13  get_chara/get_stat/set_stat/get_relation/set_relation
--                modify_relation/get_flag/set_flag/has_flag/get_inventory
--                add_item/remove_item/get_item_count
--   world.*   6  get_day/set_day/get_time/set_time/get_location/set_location
--   event.*   3  emit/listen/after_days
--   util.*    5  random/random_range/log/debug/sleep
--
-- 每条指令用 pcall 包住以捕获异常；有返回值的用 check 比对契约。
-- 结尾输出汇总，并把被改动的游戏状态恢复原值。
--
-- 注：本剧本在开发阶段默认启用（每次新游戏跑一遍）。上线前应改为 flag 门控或移除。

return {
    on_event = "on_game_start",

    execute = function()
        -- 自检仅跑一次
        if data.get_flag("selftest", "done", false) then
            return
        end

        -- ── 计数与断言工具 ──────────────────────────────
        local pass, fail = 0, 0
        local failed = {}

        local function ok(label, extra)
            pass = pass + 1
            local suffix = ""
            if extra ~= nil then
                suffix = " = " .. tostring(extra)
            end
            ui.text("   [OK] " .. label .. suffix, "green")
        end

        local function ng(label, expected, actual)
            fail = fail + 1
            failed[#failed + 1] = label
            ui.text("   [NG] " .. label .. "  期望=" .. tostring(expected)
                    .. "  实际=" .. tostring(actual), "red")
        end

        local function check(label, actual, expected)
            local good
            if type(actual) == "number" and type(expected) == "number" then
                local d = actual - expected
                good = (d < 0.0001) and (d > -0.0001)
            else
                good = tostring(actual) == tostring(expected)
            end
            if good then
                ok(label, actual)
            else
                ng(label, expected, actual)
            end
            return good
        end

        -- 无返回值的指令：只验证不抛异常
        local function call(label, fn)
            local good, err = pcall(fn)
            if good then
                ok(label)
            else
                ng(label, "无异常", tostring(err))
            end
        end

        -- ── 记录原始状态（结尾恢复）─────────────────────
        local orig_day   = world.get_day()
        local orig_time  = world.get_time()
        local orig_loc   = world.get_location()
        local orig_money = data.get_stat("player", "money")
        local orig_hp    = data.get_stat("player", "hp")

        -- ═══════════════════════════════════════════════
        -- 一、ui.* 显示与音频（13 条中的 11 条非阻塞）
        -- ═══════════════════════════════════════════════
        call("ui.clear()", function() ui.clear() end)

        ui.set_background("shrine", "fade")
        ui.text("―― 博丽神社·修行成果检验 ――", "cyan", true)
        ui.text("灵梦：出门修行之前，先把该会的都过一遍。", "pink")
        ui.show_character("reimu", "normal", "right")
        ui.play_music("selftest_bgm", 0.5, true)

        ui.text("【一】显示与音频", "yellow", true)
        call("ui.text(text,color,bold)", function() ui.text("  文本/颜色/加粗", "magenta", true) end)
        call("ui.show_image(name,pos,fade)", function() ui.show_image("selftest_chart", "left", true) end)
        call("ui.hide_image(name,fade)", function() ui.hide_image("selftest_chart") end)
        call("ui.play_sound(name,volume)", function() ui.play_sound("selftest_beep", 0.8) end)
        call("ui.stop_sound(name)", function() ui.stop_sound("selftest_beep") end)
        call("ui.play_music(name,vol,loop)", function() ui.play_music("selftest_bgm", 0.5, true) end)
        call("ui.set_background(name,trans)", function() ui.set_background("shrine", "fade") end)
        call("ui.show_character(id,expr,pos)", function() ui.show_character("marisa", "happy", "left") end)
        call("ui.hide_character(id)", function() ui.hide_character("marisa") end)
        call("ui.stop_music(fade_out)", function() ui.stop_music(false) end)
        ui.play_music("selftest_bgm", 0.5, true)

        -- ═══════════════════════════════════════════════
        -- 二、world.* （6）
        -- ═══════════════════════════════════════════════
        ui.text("【二】世界状态", "yellow", true)
        check("world.get_day() >= 1", orig_day >= 1, true)

        world.set_day(orig_day + 3)
        check("world.set_day(d+3) -> get_day", world.get_day(), orig_day + 3)

        world.set_time("night")
        check("world.set_time(night) -> get_time", world.get_time(), "night")
        world.set_time("evening")
        check("world.set_time(evening) -> get_time", world.get_time(), "evening")

        world.set_location("selftest_room")
        check("world.set_location -> get_location", world.get_location(), "selftest_room")

        world.set_day(orig_day)
        world.set_time(orig_time)
        world.set_location(orig_loc)
        check("世界状态恢复 day", world.get_day(), orig_day)
        check("世界状态恢复 location", world.get_location(), orig_loc)

        -- ═══════════════════════════════════════════════
        -- 三、data.* 角色属性与好感（6）
        -- ═══════════════════════════════════════════════
        ui.text("【三】角色属性与好感", "yellow", true)

        local reimu = data.get_chara("reimu")
        check("data.get_chara(reimu) 非 nil", reimu ~= nil, true)
        if reimu ~= nil then
            check("  .id", reimu.id, "reimu")
            check("  .name", reimu.name, "博丽灵梦")
            check("  .stats.hp", reimu.stats.hp, 120)
            check("  .stats.max_mp", reimu.stats.max_mp, 80)
            check("  .location", reimu.location, "hakurei_shrine")
        end
        check("data.get_chara(不存在) -> nil", data.get_chara("nobody") == nil, true)

        check("data.get_stat(player,max_hp)", data.get_stat("player", "max_hp"), 100)
        check("data.get_stat(player,money)", data.get_stat("player", "money"), orig_money)
        check("data.get_stat(reimu,hp)", data.get_stat("reimu", "hp"), 120)
        check("data.get_stat(未知键,default=777)",
              data.get_stat("player", "no_such_stat", 777), 777)

        data.set_stat("player", "hp", 55)
        check("data.set_stat player.hp=55", data.get_stat("player", "hp"), 55)
        data.set_stat("player", "hp", 999)
        check("data.set_stat hp 上限钳制到 max_hp", data.get_stat("player", "hp"), 100)
        data.set_stat("player", "hp", 0)
        check("data.set_stat hp 下限钳制到 0", data.get_stat("player", "hp"), 0)
        data.set_stat("player", "hp", orig_hp)

        check("data.set_stat(不存在角色) -> false",
              data.set_stat("nobody", "hp", 1), false)
        check("data.set_stat(player,relation) -> false",
              data.set_stat("player", "relation", 50), false)

        check("data.get_relation(reimu) 初始", data.get_relation("reimu"), 0)
        check("data.get_relation(player) = 0", data.get_relation("player"), 0)

        check("data.set_relation(reimu,30) -> true", data.set_relation("reimu", 30), true)
        check("  -> get_relation", data.get_relation("reimu"), 30)
        check("data.set_relation(reimu,200) -> true", data.set_relation("reimu", 200), true)
        check("  -> 上限钳制到 100", data.get_relation("reimu"), 100)
        check("data.set_relation(player) -> false", data.set_relation("player", 10), false)

        check("data.modify_relation(reimu,-40) 返回值",
              data.modify_relation("reimu", -40), 60)
        check("  -> get_relation", data.get_relation("reimu"), 60)
        check("data.modify_relation(reimu,-500) 下限钳制",
              data.modify_relation("reimu", -500), -100)

        data.set_stat("marisa", "relation", 25)
        check("data.set_stat char.relation 转发到好感",
              data.get_relation("marisa"), 25)

        data.set_relation("reimu", 0)
        data.set_relation("marisa", 10)

        -- ═══════════════════════════════════════════════
        -- 四、data.* Flag 命名空间（3 + 隔离/保护）
        -- ═══════════════════════════════════════════════
        ui.text("【四】Flag 命名空间", "yellow", true)

        check("data.set_flag -> true", data.set_flag("selftest", "k", 42), true)
        check("  -> get_flag", data.get_flag("selftest", "k"), 42)
        check("  -> has_flag", data.has_flag("selftest", "k"), true)
        check("data.get_flag 缺失键用 default",
              data.get_flag("selftest", "missing", "dflt"), "dflt")
        check("data.has_flag 缺失键", data.has_flag("selftest", "missing"), false)

        data.set_flag("mod_a", "same_key", "A")
        data.set_flag("mod_b", "same_key", "B")
        check("命名空间隔离 mod_a", data.get_flag("mod_a", "same_key"), "A")
        check("命名空间隔离 mod_b", data.get_flag("mod_b", "same_key"), "B")

        check("data.set_flag(core,..) 被拒 -> false",
              data.set_flag("core", "cheat", true), false)
        check("  -> core 未被写入", data.get_flag("core", "cheat", nil) == nil, true)

        check("data.set_flag(char:reimu,..) -> true",
              data.set_flag("char:reimu", "met", true), true)
        check("  -> get_flag", data.get_flag("char:reimu", "met"), true)
        check("  -> has_flag", data.has_flag("char:reimu", "met"), true)
        check("  -> 角色间隔离", data.has_flag("char:marisa", "met"), false)

        -- ═══════════════════════════════════════════════
        -- 五、data.* 背包（4）
        -- ═══════════════════════════════════════════════
        ui.text("【五】背包", "yellow", true)

        check("data.add_item(id,3) -> true", data.add_item("selftest_item", 3), true)
        check("  -> get_item_count", data.get_item_count("selftest_item"), 3)
        check("data.add_item 追加 2 -> true", data.add_item("selftest_item", 2), true)
        check("  -> 累加为 5", data.get_item_count("selftest_item"), 5)
        check("data.remove_item 2 -> true", data.remove_item("selftest_item", 2), true)
        check("  -> 剩余 3", data.get_item_count("selftest_item"), 3)
        check("data.remove_item 不存在 -> false", data.remove_item("no_such_item", 1), false)
        check("data.get_item_count 不存在 -> 0", data.get_item_count("no_such_item"), 0)
        check("data.add_item(count=0) -> false", data.add_item("zero_item", 0), false)

        local inv = data.get_inventory()
        check("data.get_inventory() 非 nil", inv ~= nil, true)
        check("  -> 含 selftest_item", inv["selftest_item"], 3)

        data.remove_item("selftest_item", 5)
        check("背包清理后为 0", data.get_item_count("selftest_item"), 0)

        -- ═══════════════════════════════════════════════
        -- 六、event.* （3）
        -- ═══════════════════════════════════════════════
        ui.text("【六】事件", "yellow", true)

        local fired = 0
        event.listen("custom:selftest_ping", function() fired = fired + 1 end)
        event.emit("custom:selftest_ping")
        check("event.listen + event.emit 触发 1 次", fired, 1)
        event.emit("custom:selftest_ping")
        check("再次 emit -> 累计 2 次", fired, 2)

        -- payload 透传（pcall 保护：即使实现丢弃 payload 也不会中断剧本）
        local got = "未收到"
        event.listen("custom:selftest_payload", function(ctx)
            local read_ok, v = pcall(function()
                if ctx == nil or ctx.data == nil then
                    return nil
                end
                return ctx.data["score"]
            end)
            if read_ok and v ~= nil then
                got = tostring(v)
            end
        end)
        event.emit("custom:selftest_payload", { score = 42 })
        check("event.emit payload 透传 score", got, "42")

        call("event.after_days(3,fn) 不抛异常", function()
            event.after_days(3, function() ui.text("（3 天后回调）", "gray") end)
        end)
        ui.text("   [INFO] event.after_days 为惰性占位，不会真正延迟触发", "gray")

        -- ═══════════════════════════════════════════════
        -- 七、util.* （5）
        -- ═══════════════════════════════════════════════
        ui.text("【七】工具", "yellow", true)

        local r = util.random()
        check("util.random() 落在 [0,1)", (r >= 0) and (r < 1), true)

        local rr = util.random_range(10, 20)
        check("util.random_range(10,20) 在区间内", (rr >= 10) and (rr <= 20), true)

        local rlo = util.random_range(20, 10)
        check("util.random_range(20,10) 反序自动交换", (rlo >= 10) and (rlo <= 20), true)

        call("util.log(msg)", function() util.log("selftest: util.log 正常") end)
        call("util.debug(msg)", function() util.debug("selftest: util.debug 正常") end)
        call("util.sleep(0.1)", function() util.sleep(0.1) end)

        -- ═══════════════════════════════════════════════
        -- 八、阻塞交互（ui.ask_choice / ui.ask_input）
        -- ═══════════════════════════════════════════════
        ui.text("【八】玩家交互", "yellow", true)
        ui.text("灵梦：最后，回答我两个问题。", "pink")

        local c = ui.ask_choice({ "（干脆地）准备好了", "（犹豫）还没", "（沉默）" })
        check("ui.ask_choice 返回 1..3", (c >= 1) and (c <= 3), true)
        ui.text("灵梦：……你的回答是第 " .. tostring(c) .. " 项。", "pink")

        local name = ui.ask_input("报上名号：", "无名氏", 20)
        check("ui.ask_input 返回 string", type(name) == "string", true)
        ui.text("灵梦：原来叫「" .. tostring(name) .. "」啊。", "pink")

        -- ═══════════════════════════════════════════════
        -- 九、汇总
        -- ═══════════════════════════════════════════════
        ui.text("", "white")
        ui.text("―― 检验结果 ――", "cyan", true)
        local tone = "green"
        if fail > 0 then
            tone = "red"
        end
        ui.text("通过 " .. tostring(pass) .. " 项 / 失败 " .. tostring(fail) .. " 项", tone, true)
        if fail > 0 then
            for i = 1, #failed do
                ui.text("  ✗ " .. failed[i], "red")
            end
        end

        ui.text("【已知契约偏差（记录，不判失败）】", "yellow", true)
        ui.text("  · world.set_time / set_location 不自动 emit on_time_change / on_location_change", "gray")
        ui.text("  · event.after_days 为惰性占位，不会真正定时触发", "gray")

        -- ── 恢复状态 ────────────────────────────────────
        world.set_day(orig_day)
        world.set_time(orig_time)
        world.set_location(orig_loc)
        data.set_stat("player", "money", orig_money)
        data.set_stat("player", "hp", orig_hp)
        data.set_relation("reimu", 0)
        data.set_relation("marisa", 10)

        ui.hide_character("reimu")
        ui.stop_music(true)
        ui.text("灵梦：行了，出发吧。", "pink")

        data.set_flag("selftest", "done", true)
    end
}
