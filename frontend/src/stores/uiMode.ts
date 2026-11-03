/**
 * UI 模式状态机（纯函数，无 Vue/Pinia 依赖）。
 *
 * 设计约束（对应 docs/planning 的 UI 空壳修复）：
 * 1. 根界面只有三种：主菜单 / Hub / 叙事游戏。系统界面（存档/设置/角色详情）
 *    全部是 `panel` 悬浮层，不再进入 `uiMode`。
 * 2. 模式栈只为覆盖层（当前是小游戏）服务，栈里保存的是被覆盖的根界面。
 * 3. 空栈 pop 是 no-op，**绝不**回退到隐式的 `game`——那会得到一个没有内容的空壳。
 */

export type BaseMode = 'main_menu' | 'hub' | 'game'
export type OverlayMode = 'minigame'
export type UiMode = BaseMode | OverlayMode

export interface UiModeState {
  mode: UiMode
  stack: UiMode[]
}

export const BASE_MODES: readonly BaseMode[] = ['main_menu', 'hub', 'game']

export function isBaseUiMode(mode: UiMode): mode is BaseMode {
  return (BASE_MODES as readonly string[]).includes(mode)
}

export function isOverlayUiMode(mode: UiMode): mode is OverlayMode {
  return mode === 'minigame'
}

/** 运行时兜底：后端/旧代码可能塞进来非法字符串 */
export function isValidUiMode(value: unknown): value is UiMode {
  return typeof value === 'string' && (isBaseUiMode(value as UiMode) || isOverlayUiMode(value as UiMode))
}

/** 压入覆盖层；重复压入同一个模式是 no-op（防止重复的 minigame.start 叠栈） */
export function pushUiState(state: UiModeState, mode: OverlayMode): UiModeState {
  if (state.mode === mode) return state
  return { mode, stack: [...state.stack, state.mode] }
}

/** 弹出覆盖层；空栈返回原状态，不猜测“应该回到哪” */
export function popUiState(state: UiModeState): UiModeState {
  if (state.stack.length === 0) return state
  const stack = [...state.stack]
  const mode = stack.pop() as UiMode
  return { mode, stack }
}

/** 根界面切换：清空模式栈 */
export function resetUiState(mode: BaseMode): UiModeState {
  return { mode, stack: [] }
}
