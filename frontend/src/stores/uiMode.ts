/**
 * 根界面状态（纯函数/类型，无 Vue/Pinia 依赖）。
 *
 * P3 起 UI 分成两层：
 * - 根界面（本文件）：main_menu / hub / game，只有这三个页面级模式；
 * - Overlay Host（store.overlay）：独立 UI 模块（小游戏是第一个），
 *   覆盖在当前根界面上，不改变 uiMode，也不卸载主界面。
 *
 * 因此这里不再有 minigame 模式与模式栈；历史空壳问题由
 * ADR-0008 的“合法根模式 + 可见恢复页”继续兜底。
 */

export type BaseMode = 'main_menu' | 'hub' | 'game'
export type UiMode = BaseMode

export const BASE_MODES: readonly BaseMode[] = ['main_menu', 'hub', 'game']

export function isBaseUiMode(mode: UiMode): mode is BaseMode {
  return (BASE_MODES as readonly string[]).includes(mode)
}

/** 运行时兜底：旧状态/外部写入可能塞进来非法字符串 */
export function isValidUiMode(value: unknown): value is UiMode {
  return typeof value === 'string' && (BASE_MODES as readonly string[]).includes(value)
}
