/**
 * 游戏状态 store —— 前端唯一状态源（视图在客户端，状态在服务端 ADR-0003）
 * 消息处理对应后端 ws_gateway 的推送。
 */
import { defineStore } from 'pinia'
import { wsClient } from '../ws/client'

/** 静态资源基地址（后端 main.py 的静态服务，默认 127.0.0.1:8766） */
export const ASSET_BASE = 'http://127.0.0.1:8766'

export type UiMode = 'main_menu' | 'game' | 'settings' | 'save' | 'load' | 'character_detail' | 'minigame'

export interface TextLine {
  text: string
  color: string | null
  bold: boolean
}

export interface StatusData {
  day: number
  time_of_day: string
  location: string
  player: {
    hp: number
    max_hp: number
    mp: number
    max_mp: number
    stamina: number
    max_stamina: number
    money: number
    level: number
  }
  characters: Record<string, { name: string; relation: number }>
}

export interface SaveMeta {
  version: string
  save_time: string
  day: number
  location: string
  description: string
  playtime: number
}

export interface SaveSlotInfo {
  slot_id: number
  exists: boolean
  metadata: SaveMeta | null
}

export interface Choice {
  requestId: string
  options: string[]
}

export interface CharacterView {
  charId: string
  expression: string
  position: string
}

export interface InputRequest {
  requestId: string
  prompt: string
  default: string
  maxLength: number
}

interface GameState {
  uiMode: UiMode
  /** UI 模式栈（v1 PRD push_mode/pop_mode 语义）：子界面返回上一模式 */
  modeStack: UiMode[]
  wsUrl: string
  connected: boolean
  textFlow: TextLine[]
  choice: Choice | null
  input: InputRequest | null
  background: string | null
  characters: Map<string, CharacterView>
  awaitingChoice: boolean
  status: StatusData | null
  saves: SaveSlotInfo[]
  toast: string | null
  /** 当前小游戏（DSL 触发带 requestId 回传；主菜单测试入口无 requestId） */
  activeMinigame: { gameId: string; requestId: string | null } | null
  /** 文本区是否空闲（无打印、无待确认段落）——选项/输入框只在空闲时出现 */
  textIdle: boolean
  /** 文本推进信号（GameScreen 点击委托递增，TextFlow 监听推进段落） */
  textAdvanceTick: number
}

const DEFAULT_WS = 'ws://127.0.0.1:8765'

export const useGameStore = defineStore('game', {
  state: (): GameState => ({
    uiMode: 'main_menu',
    modeStack: [],
    wsUrl: DEFAULT_WS,
    connected: false,
    textFlow: [],
    choice: null,
    input: null,
    background: null,
    characters: new Map(),
    awaitingChoice: false,
    status: null,
    saves: [],
    toast: null,
    activeMinigame: null,
    textIdle: true,
    textAdvanceTick: 0,
  }),

  actions: {
    /** 建立 WS 连接并注册协议处理器 */
    connect(): void {
      wsClient.connect(this.wsUrl).then(() => {
        this.connected = true
        // 拉取存档列表（主菜单"继续游戏"可用性判断）
        wsClient.send({ type: 'game.list_saves' })
      }).catch((e) => {
        console.error('[store] 连接失败', e)
        this.connected = false
      })

      wsClient.on('ui.text', (m) => {
        const p = (m.payload ?? {}) as { text?: string; color?: string | null; bold?: boolean }
        this.textFlow.push({
          text: p.text ?? '',
          color: p.color ?? null,
          bold: !!p.bold,
        })
        this.scrollToBottom()
      })
      wsClient.on('ui.clear', () => {
        this.textFlow = []
      })
      wsClient.on('ui.ask_choice', (m) => {
        const p = (m.payload ?? {}) as { options?: unknown[] }
        this.choice = {
          requestId: m.requestId ?? '',
          options: (p.options ?? []).map(String),
        }
        this.awaitingChoice = true
      })
      wsClient.on('ui.ask_input', (m) => {
        const p = (m.payload ?? {}) as { prompt?: string; default?: string; max_length?: number }
        this.input = {
          requestId: m.requestId ?? '',
          prompt: p.prompt ?? '',
          default: p.default ?? '',
          maxLength: p.max_length ?? 100,
        }
      })
      wsClient.on('ui.background_set', (m) => {
        const p = (m.payload ?? {}) as { name?: string }
        this.background = p.name ?? null
      })
      wsClient.on('ui.character_show', (m) => {
        const p = (m.payload ?? {}) as { char_id?: string; expression?: string; position?: string }
        if (p.char_id) {
          this.characters.set(p.char_id, {
            charId: p.char_id,
            expression: p.expression ?? 'normal',
            position: p.position ?? 'center',
          })
        }
      })
      wsClient.on('ui.character_hide', (m) => {
        const p = (m.payload ?? {}) as { char_id?: string }
        if (p.char_id) this.characters.delete(p.char_id)
      })
      wsClient.on('__connection_closed', () => {
        this.connected = false
      })
      wsClient.on('status.sync', (m) => {
        this.status = (m.payload ?? {}) as unknown as StatusData
      })
      wsClient.on('saves.list', (m) => {
        this.saves = ((m.payload ?? {}).slots ?? []) as unknown as SaveSlotInfo[]
      })
      wsClient.on('save.result', (m) => {
        const p = (m.payload ?? {}) as { ok?: boolean; slot_id?: number }
        this.showToast(p.ok ? `已保存到槽位 ${p.slot_id}` : '保存失败')
      })
      wsClient.on('load.result', (m) => {
        const p = (m.payload ?? {}) as { ok?: boolean }
        if (p.ok) {
          this.showToast('读档成功')
          this.textFlow = []
          this.choice = null
          this.input = null
          this.background = null
          this.characters.clear()
        } else {
          this.showToast('读档失败')
        }
      })
      // 小游戏触发（DSL minigame.start）：进入 minigame 模式
      wsClient.on('minigame.start', (m) => {
        const p = (m.payload ?? {}) as { game_id?: string }
        this.pushMode('minigame')
        this.activeMinigame = { gameId: p.game_id ?? '', requestId: m.requestId ?? null }
      })
    },

    showToast(message: string): void {
      this.toast = message
      setTimeout(() => {
        this.toast = null
      }, 2200)
    },

    /** 开始新游戏 */
    startGame(): void {
      this.uiMode = 'game'
      this.textFlow = []
      this.choice = null
      this.input = null
      this.background = null
      this.characters.clear()
      wsClient.send({ type: 'game.start' })
    },

    /** 返回主菜单（清栈 + 通知后端中止挂起脚本，释放游戏线程） */
    backToMenu(): void {
      this.uiMode = 'main_menu'
      this.modeStack = []
      wsClient.send({ type: 'game.abort' })
    },

    /** ── UI 模式栈（push/pop，子界面返回上一模式）────────── */
    pushMode(mode: UiMode): void {
      this.modeStack.push(this.uiMode)
      this.uiMode = mode
    },

    popMode(): void {
      this.uiMode = this.modeStack.pop() ?? 'game'
    },

    /** ── 存档界面（模式栈：save/load）────────────────── */
    openSave(): void {
      this.pushMode('save')
      wsClient.send({ type: 'game.list_saves' })
    },

    openLoad(): void {
      this.pushMode('load')
      wsClient.send({ type: 'game.list_saves' })
    },

    closeMenu(): void {
      this.popMode()
    },

    openSettings(): void {
      this.pushMode('settings')
    },

    openMinigame(): void {
      // 主菜单测试入口（无 requestId，结果不回传脚本）
      this.pushMode('minigame')
      this.activeMinigame = { gameId: 'slime_battle', requestId: null }
    },

    /** 小游戏结束：回传结果给后端（DSL 触发时）并返回上一模式 */
    finishMinigame(result: Record<string, unknown>): void {
      const mg = this.activeMinigame
      if (mg?.requestId) {
        wsClient.send({
          type: 'minigame.result',
          requestId: mg.requestId,
          payload: { result },
        })
      } else {
        this.showToast(result.won ? '小游戏胜利！' : '小游戏结束')
      }
      this.activeMinigame = null
      this.popMode()
    },

    saveToSlot(slotId: number): void {
      wsClient.send({
        type: 'game.save',
        payload: { slot_id: slotId, description: `第${this.status?.day ?? 1}天存档` },
      })
      this.uiMode = 'game'
    },

    quickSave(): void {
      wsClient.send({ type: 'game.quick_save' })
      this.uiMode = 'game'
    },

    loadFromSlot(slotId: number): void {
      wsClient.send({ type: 'game.load', payload: { slot_id: slotId } })
      this.uiMode = 'game'
    },

    quickLoad(): void {
      wsClient.send({ type: 'game.quick_load' })
      this.uiMode = 'game'
    },

    deleteSave(slotId: number): void {
      wsClient.send({ type: 'game.delete_save', payload: { slot_id: slotId } })
      this.showToast('存档已删除')
    },

    /** 玩家点击游戏画面：推进文本（背景/文本区委托） */
    advanceText(): void {
      this.textAdvanceTick++
    },

    /** 玩家选择选项（1-based index） */
    choose(index: number): void {
      if (!this.choice) return
      wsClient.send({
        type: 'choice.made',
        requestId: this.choice.requestId,
        payload: { index },
      })
      this.choice = null
      this.awaitingChoice = false
    },

    /** 提交文字输入 */
    submitInput(text: string): void {
      if (!this.input) return
      wsClient.send({
        type: 'input.submit',
        requestId: this.input.requestId,
        payload: { text },
      })
      this.input = null
    },

    scrollToBottom(): void {
      // 由 TextFlow 组件通过 watch 处理滚动
    },
  },
})
