import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useGameStore, type HubButton } from './game'
import { wsClient } from '../ws/client'
import type { WsMessage } from '../ws/client'

/** 直接投递一条 WS 消息（模拟后端推送），避免起真实连接 */
function dispatch(msg: WsMessage): void {
  ;(wsClient as unknown as { dispatch(m: WsMessage): void }).dispatch(msg)
}

function hubButton(overrides: Partial<HubButton> = {}): HubButton {
  return {
    char: 'reimu',
    label: '去神社看看',
    event: 'story:reimu_01',
    order: 30,
    available: true,
    reason: null,
    stamina_cost: 0,
    daily_limit: 0,
    used_today: null,
    ...overrides,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  wsClient.clearHandlers()
  vi.spyOn(wsClient, 'send').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'debug').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('UI 模式栈', () => {
  it('小游戏正常打开/返回：回到打开它的那个界面', () => {
    const s = useGameStore()
    s.uiMode = 'main_menu'

    s.openMinigame()
    expect(s.uiMode).toBe('minigame')
    expect(s.modeStack).toEqual(['main_menu'])

    s.finishMinigame({ won: true })
    expect(s.uiMode).toBe('main_menu')
    expect(s.modeStack).toEqual([])
  })

  it('空栈 pop 不会回退到 game（避免默认空壳）', () => {
    const s = useGameStore()
    s.uiMode = 'hub'
    s.modeStack = []

    s.popMode()

    expect(s.uiMode).toBe('hub')
  })

  it('小游戏「返回」重复触发是幂等的，不会二次 pop', () => {
    const s = useGameStore()
    s.uiMode = 'main_menu'
    s.openMinigame()

    s.finishMinigame({ won: true })
    s.finishMinigame({ won: true })

    expect(s.uiMode).toBe('main_menu')
    expect(s.modeStack).toEqual([])
  })

  it('记录 UI 状态转移（from/to/栈/来源）', () => {
    const s = useGameStore()
    s.uiMode = 'main_menu'

    s.openMinigame()

    const last = s.uiTransitions[s.uiTransitions.length - 1]
    expect(last).toMatchObject({
      fromMode: 'main_menu',
      toMode: 'minigame',
      action: 'push',
      source: 'user',
    })
    expect(last.stackAfter).toEqual(['main_menu'])
  })
})

describe('过期的 WebSocket 消息', () => {
  it('主菜单收到迟到的 event.done 不会强行切到 Hub', () => {
    const s = useGameStore()
    s.uiMode = 'main_menu'
    s.bindHandlers()

    dispatch({ type: 'event.done', payload: { event: 'story:reimu_01' } })

    expect(s.uiMode).toBe('main_menu')
  })

  it('Hub 行动被后端拒绝且页面无内容时，回到 Hub 而不是停在空壳', () => {
    const s = useGameStore()
    s.uiMode = 'hub'
    s.bindHandlers()

    s.chooseHubButton(hubButton())
    expect(s.uiMode).toBe('game')
    expect(s.textFlow).toHaveLength(0)

    dispatch({
      type: 'event.result',
      payload: { ok: false, event: 'story:reimu_01', reason: '对话进行中，请先完成当前对话' },
    })

    expect(s.uiMode).toBe('hub')
    expect(s.textFlow).toHaveLength(0)
  })

  it('旧事件的 event.done 不会结束当前新事件', () => {
    const s = useGameStore()
    s.uiMode = 'game'
    s.pendingEvent = { name: 'story:reimu_02', epoch: s.uiEpoch }
    s.bindHandlers()

    dispatch({ type: 'event.done', payload: { event: 'story:reimu_01' } })

    expect(s.uiMode).toBe('game')
    expect(s.eventFinished).toBe(false)
    expect(s.pendingEvent?.name).toBe('story:reimu_02')
  })

  it('当前事件的 event.done 且无内容时回 Hub', () => {
    const s = useGameStore()
    s.uiMode = 'game'
    s.pendingEvent = { name: 'on_game_start', epoch: s.uiEpoch }
    s.bindHandlers()

    dispatch({ type: 'event.done', payload: { event: 'on_game_start' } })

    expect(s.uiMode).toBe('hub')
    expect(s.pendingEvent).toBeNull()
  })

  it('自检从 Hub 切到叙事界面（否则选项无处显示）', () => {
    const s = useGameStore()
    s.uiMode = 'hub'

    s.runSelftest()

    expect(s.uiMode).toBe('game')
    expect(s.pendingEvent?.name).toBe('custom:run_selftest')
  })

  it('睡觉 → 叙事界面 → day_advance 结束信号 → Hub', () => {
    const s = useGameStore()
    s.uiMode = 'hub'
    s.bindHandlers()

    dispatch({ type: 'sleep.result', payload: { ok: true } })
    expect(s.uiMode).toBe('game')
    expect(s.pendingEvent?.name).toBe('day_advance')

    dispatch({ type: 'event.done', payload: { event: 'day_advance' } })
    expect(s.uiMode).toBe('hub')
  })

  it('主菜单收到迟到的 sleep.result 不会切进空游戏页', () => {
    const s = useGameStore()
    s.uiMode = 'main_menu'
    s.bindHandlers()

    dispatch({ type: 'sleep.result', payload: { ok: true } })

    expect(s.uiMode).toBe('main_menu')
  })

  it('主菜单收到迟到的 minigame.start 不会顶掉主菜单', () => {
    const s = useGameStore()
    s.uiMode = 'main_menu'
    s.bindHandlers()

    dispatch({ type: 'minigame.start', payload: { game_id: 'slime_battle' } })

    expect(s.uiMode).toBe('main_menu')
    expect(s.activeMinigame).toBeNull()
  })

  it('界面已切换后，迟到的读档结果被丢弃', () => {
    const s = useGameStore()
    s.uiMode = 'game'
    s.panel = 'load'
    s.bindHandlers()

    s.loadFromSlot(1)
    s.backToMenu()
    dispatch({ type: 'load.result', payload: { ok: true, dialogue: [] } })

    expect(s.uiMode).toBe('main_menu')
  })

  it('读档成功后关闭读档面板（读档完整结束）', () => {
    const s = useGameStore()
    s.uiMode = 'game'
    s.panel = 'load'
    s.bindHandlers()

    s.loadFromSlot(1)
    dispatch({ type: 'load.result', payload: { ok: true, dialogue: [] } })

    expect(s.uiMode).toBe('hub')
    expect(s.panel).toBeNull()
  })
})
