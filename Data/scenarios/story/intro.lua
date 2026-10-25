-- 主线事件：序章
-- 游戏开始时的第一个事件

return {
    on_event = "on_game_start",

    execute = function()
        -- 事件仅在首次触发
        if data.get_flag("story", "intro_completed", false) then
            return
        end

        -- 开场
        ui.clear()
        ui.set_background("shrine", "fade")
        ui.text("――幻想乡，一个被遗忘了的世界。", "white", true)
        util.sleep(1.0)
        ui.text("博丽神社的早晨，一如既往地安静。", "cyan")
        util.sleep(0.5)

        -- 显示灵梦
        ui.show_character("reimu", "normal", "right")
        ui.text("灵梦：啊——今天也没什么要紧事呢。", "pink")
        ui.text("灵梦：来杯茶，发发呆，一天就过去了。", "pink")

        -- 玩家选项
        local choice = ui.ask_choice({"去村里转转", "在神社帮忙", "去魔法森林探险", "帮灵梦清理异变"})

        if choice == 1 then
            ui.text("你决定去村里的市集看看。", "white")
            data.set_flag("story", "first_choice", "village")
        elseif choice == 2 then
            ui.text("你决定帮灵梦打扫神社。", "white")
            data.set_flag("story", "first_choice", "shrine")
            data.modify_relation("reimu", 3)
        elseif choice == 3 then
            ui.text("你决定去魔法森林探险。", "white")
            data.set_flag("story", "first_choice", "forest")
        else
            -- 选择 4：帮灵梦清理异变 → 史莱姆战斗小游戏
            ui.text("灵梦：诶？你要帮忙吗？", "pink")
            ui.text("灵梦：太好了！森林里的妖怪最近很不安分……", "pink")
            util.sleep(0.5)
            ui.text("灵梦：那就拜托你了！", "pink")
            ui.show_character("reimu", "happy", "right")

            local result = minigame.start("slime_battle", { hp = 40 })
            if result.won then
                ui.text("灵梦：太厉害了！一下子就把它们打跑了！", "pink")
                data.set_flag("story", "first_choice", "exorcism")
                data.modify_relation("reimu", 10)
                data.modify_stat("player", "money", result.score or 20)
            else
                ui.text("灵梦：没事没事，妖怪们只是闹着玩的。", "pink")
                data.set_flag("story", "first_choice", "exorcism_failed")
            end
        end

        ui.text("新的旅程开始了……", "yellow", true)

        -- 标记事件完成
        data.set_flag("story", "intro_completed", true)
        ui.hide_character("reimu")
    end
}
