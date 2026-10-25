-- 角色剧本：博丽灵梦 · 特殊行动「一起修行」
-- Hub 入口：选中灵梦 → 「一起修行」
-- 演示数值条件：好感 < 10 时按钮不可用（前端置灰并提示原因）

return {
    on_event = "action:reimu_training",

    hub = {
        char = "reimu",
        label = "一起修行",
        order = 20,
        require_relation = 10,
    },

    execute = function()
        ui.set_background("shrine", "fade")
        ui.show_character("reimu", "serious", "center")
        ui.text("灵梦：修行啊……行，正好我也活动活动。", "pink")

        local r = util.random_range(1, 10)
        if r <= 6 then
            ui.text("在灵梦的指导下练了一套退魔手法。", "white")
            ui.text("（经验 +10，好感 +2）", "gray")
            data.modify_stat("player", "exp", 10)
            data.modify_relation("reimu", 2)
        else
            ui.text("被灵梦轻松打趴下了。", "red")
            ui.text("灵梦：还差得远呢。", "pink")
            data.modify_stat("player", "hp", -10)
            data.modify_relation("reimu", 1)
        end

        ui.hide_character("reimu")
    end
}
