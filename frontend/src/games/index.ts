/**
 * 小游戏注册表 —— 独立模块（对齐角色/剧本的外部模块理念）
 * 新增小游戏：实现组件并在此注册即可，无需改引擎代码。
 */
import type { Component } from 'vue'
import SlimeBattle from './SlimeBattle.vue'

export interface MinigameDef {
  /** 唯一 id（DSL 用 minigame.start("id") 触发） */
  id: string
  title: string
  component: Component
}

export const minigames: MinigameDef[] = [
  { id: 'slime_battle', title: '史莱姆战斗', component: SlimeBattle },
]

export function findMinigame(id: string): MinigameDef | undefined {
  return minigames.find((m) => m.id === id)
}
