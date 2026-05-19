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
        local choice = ui.ask_choice({"去村里转转", "在神社帮忙", "去魔法森林探险"})

        if choice == 1 then
            ui.text("你决定去村里的市集看看。", "white")
            data.set_flag("story", "first_choice", "village")
        elseif choice == 2 then
            ui.text("你决定帮灵梦打扫神社。", "white")
            data.set_flag("story", "first_choice", "shrine")
            data.set_stat("reimu", "relation", 3)
        else
            ui.text("你决定去魔法森林探险。", "white")
            data.set_flag("story", "first_choice", "forest")
        end

        ui.text("新的旅程开始了……", "yellow", true)

        -- 标记事件完成
        data.set_flag("story", "intro_completed", true)
        ui.hide_character("reimu")
    end
}
