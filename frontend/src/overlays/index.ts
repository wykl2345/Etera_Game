/**
 * Overlay 模块注册表（P3）。
 *
 * 每个模块是独立的 Vue 组件，由 OverlayHost 以：
 *   <component :is="def.component" :input="overlay.input"
 *              @complete="..." @cancel="..." />
 * 挂载在根界面之上。模块只依赖 input/complete/cancel，不直接改 uiMode。
 *
 * 目前只有小游戏；P4 可在这里注册非小游戏模块，并复用同一份结果回传契约。
 */
import type { Component } from 'vue'
import MinigameHost from '../components/MinigameHost.vue'

export interface OverlayModuleDef {
  id: string
  title: string
  component: Component
}

const modules = new Map<string, OverlayModuleDef>()

export function registerOverlay(def: OverlayModuleDef): void {
  modules.set(def.id, def)
}

export function findOverlay(id: string): OverlayModuleDef | undefined {
  return modules.get(id)
}

export function listOverlays(): OverlayModuleDef[] {
  return [...modules.values()]
}

registerOverlay({
  id: 'minigame',
  title: '小游戏',
  component: MinigameHost,
})
