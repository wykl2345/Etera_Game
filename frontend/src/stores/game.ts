/**
 * 游戏状态 store —— 前端唯一状态源（视图在客户端，状态在服务端 ADR-0003）
 * 消息处理对应后端 ws_gateway 的推送。
 */
import { defineStore } from 'pinia'
import { wsClient } from '../ws/client'

/** 静态资源基地址（后端 main.py 的静态服务，默认 127.0.0.1:8766） */
export const ASSET_BASE = 'http://127.0.0.1:8766'

export type UiMode = 'main_menu' | 'game' | 'settings' | 'save' | 'load' | 'character_detail'

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
}

const DEFAULT_WS = 'ws://127.0.0.1:8765'

export const useGameStore = defineStore('game', {
  state: (): GameState => ({
    uiMode: 'main_menu',
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
  }),

  actions: {
    /** 建立 WS 连接并注册协议处理器 */
    connect(): void {
      wsClient.connect(this.wsUrl).then(() => {
        this.connected = true
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

    /** 返回主菜单 */
    backToMenu(): void {
      this.uiMode = 'main_menu'
    },

    /** ── 存档界面（模式栈：save/load）────────────────── */
    openSave(): void {
      this.uiMode = 'save'
      wsClient.send({ type: 'game.list_saves' })
    },

    openLoad(): void {
      this.uiMode = 'load'
      wsClient.send({ type: 'game.list_saves' })
    },

    closeMenu(): void {
      this.uiMode = 'game'
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
