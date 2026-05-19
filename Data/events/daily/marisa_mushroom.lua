-- 测试角色事件：魔理沙的蘑菇采集
-- 测试覆盖: ui.* / data.* / util.* / world.* / event.*
-- 位置: Data/events/daily/marisa_mushroom.lua

return {
    on_event = "on_day_begin",

    execute = function()
        -- ▼ 条件1：必须已经完成序章
        if not data.has_flag("story", "intro_completed") then
            return
        end

        -- ▼ 条件2：必须在第3天之后
        if world.get_day() < 3 then
            return
        end

        -- ▼ 条件3：不能重复触发
        if data.get_flag("mushroom_test", "triggered", false) then
            return
        end

        -- ▼ 条件4：魔理沙这个角色必须存在
        local marisa = data.get_chara("marisa")
        if not marisa then
            util.log("[蘑菇事件] 魔理沙角色未加载")
            return
        end

        -- ▼ 条件5：50%概率触发
        if util.random() < 0.5 then
            return
        end

        -- ═══════════════════════════════════════
        --  事件正文
        -- ═══════════════════════════════════════

        -- 更新位置信息
        world.set_location("magic_forest")

        -- 显示场景和角色
        ui.set_background("forest", "fade")
        util.sleep(0.8)
        ui.show_character("marisa", "grin", "left")
        util.sleep(0.3)

        -- 对话
        ui.text("魔法森林的清晨，空气中弥漫着蘑菇的香味。", "white")
        util.sleep(0.5)
        ui.text("魔理沙：哟！来得正好 da☆ze！", "yellow", true)
        util.sleep(0.3)
        ui.text("魔理沙：我正在找一种会发光的蘑菇，帮我一起找吧？", "yellow")

        -- ▼ 玩家选择
        local choice = ui.ask_choice({
            "帮忙找蘑菇",
            "（沉默地走开）",
            "问她蘑菇有什么用"
        })

        if choice == 1 then
            -- 路线A：帮忙
            ui.text("你卷起袖子，和魔理沙一起在树根下翻找。", "white")
            util.sleep(0.5)

            -- 利用随机数决定找到几个蘑菇
            local found = util.random_range(1, 5)
            ui.text(string.format("找到了 %d 个发光蘑菇！", found), "green")

            data.add_item("glowing_mushroom", found)

            -- 魔理沙好感大幅上升
            local new_rel = data.modify_relation("marisa", 10)
            ui.text("魔理沙：太感谢了！这下实验材料齐了！", "yellow", true)
            ui.text("（魔理沙的好感度上升了！现在: " .. new_rel .. "）", "cyan")

        elseif choice == 2 then
            -- 路线B：走开
            ui.text("你什么都没说，转身离开了。", "gray")
            util.sleep(0.5)
            ui.text("魔理沙：……诶？就这样走了吗？", "yellow")
            data.modify_relation("marisa", -2)
            ui.text("（魔理沙似乎有点失落……）", "gray")

        else
            -- 路线C：询问
            ui.text("你问她蘑菇有什么用。", "white")
            util.sleep(0.3)
            ui.text("魔理沙：当然是做魔法实验啊！", "yellow")
            ui.text("魔理沙：听说用这种蘑菇炼制的药剂，", "yellow")
            ui.text("　　　　能让扫帚飞起来的速度提升三倍！", "yellow")
            util.sleep(0.5)
            ui.text("你半信半疑地点了点头。", "white")

            -- 好感微增
            data.modify_relation("marisa", 3)
            ui.text("（魔理沙对你的好奇心感到高兴）", "cyan")
        end

        -- ▼ 收尾
        util.sleep(0.5)
        ui.hide_character("marisa")

        -- 标记事件已触发
        data.set_flag("mushroom_test", "triggered", true)
        data.set_flag("mushroom_test", "day_triggered", world.get_day())
        data.set_flag("mushroom_test", "choice_made", choice)

        -- 发射自定义事件（供其他Mod监听）
        event.emit("custom:mushroom_event_complete", {
            choice = choice,
            day = world.get_day()
        })

        util.log("[蘑菇事件] 执行完成，选项=" .. choice)
    end
}
