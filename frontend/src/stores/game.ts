/**
 * 游戏状态 store —— 前端唯一状态源（视图在客户端，状态在服务端 ADR-0003）
 * 消息处理对应后端 ws_gateway 的推送。
 */
import { defineStore } from 'pinia'
import { nextTick } from 'vue'
import { wsClient } from '../ws/client'
import { type BaseMode, type UiMode } from './uiMode'

export type { UiMode } from './uiMode'

/**
 * 开发用端口覆盖：?wsPort=8767&assetPort=8768
 * 默认仍为 8765/8766；用于本机有旧进程占用端口时快速换端口测试。
 */
function endpointPort(name: string, fallback: number): number {
  if (typeof window === 'undefined') return fallback
  const raw = new URLSearchParams(window.location.search).get(name)
  const port = raw ? Number(raw) : NaN
  return Number.isInteger(port) && port > 0 && port < 65536 ? port : fallback
}

const WS_PORT = endpointPort('wsPort', 8765)

/** 静态资源基地址（后端 main.py 的静态服务，默认 127.0.0.1:8766） */
export const ASSET_BASE = `http://127.0.0.1:${endpointPort('assetPort', 8766)}`

export type UiTransitionAction = 'reset' | 'overlay-open' | 'overlay-close'
export type UiTransitionSource = 'user' | 'ws' | 'system' | 'component'

/** 覆盖层实例：独立 UI 模块（当前只有小游戏），不改变根界面 uiMode */
export interface OverlayInstance {
  /** 每次打开唯一；用于丢弃旧实例的迟到回调 */
  id: string
  /** 模块 id，对应 overlays/ 注册表 */
  moduleId: string
  /** 传给模块的初始化数据（必须可序列化） */
  input: Record<string, unknown>
  /** DSL 触发的 requestId；主菜单测试入口为 null */
  requestId: string | null
}

export type OverlayStatus = 'completed' | 'cancelled' | 'failed'

/** 一次 UI 状态转移（用于 200 条环形缓冲与问题取证） */
export interface UiTransition {
  time: string
  action: UiTransitionAction
  source: UiTransitionSource
  fromMode: UiMode
  toMode: UiMode
  overlay: { id: string; moduleId: string } | null
  reason?: string
  content: {
    texts: number
    choices: number
    hasInput: boolean
    background: string | null
    characters: number
    panel: string | null
    overlay: string | null
  }
}

const UI_LOG_LIMIT = 200
/** 覆盖层实例序号（模块级，不需要响应式） */
let overlaySeq = 0

/** 调试开关：开发模式默认开；生产用 localStorage.setItem('etera.uiDebug','1') */
function uiDebugEnabled(): boolean {
  try {
    const env = (import.meta as unknown as { env?: { DEV?: boolean } }).env
    if (env?.DEV) return true
  } catch {
    // 非 Vite 环境（如纯 Node）忽略
  }
  try {
    return typeof localStorage !== 'undefined' && localStorage.getItem('etera.uiDebug') === '1'
  } catch {
    return false
  }
}

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

/** Hub 角色卡片 */
export interface HubCharacter {
  char_id: string
  name: string
  relation: number
  location: string
}

/** Hub 行动按钮（由剧本注册：char/label/event/order + 可用性） */
export interface HubButton {
  char: string
  label: string
  event: string
  order: number
  available: boolean
  reason: string | null
  /** 消耗体力（0 = 不耗） */
  stamina_cost: number
  /** 每日次数上限（0 = 不限） */
  daily_limit: number
  /** 今天已用次数（无上限时为 null） */
  used_today: number | null
}

/** 可达地点（移动目标） */
export interface SceneLink {
  id: string
  name: string
  desc: string
  can_sleep: boolean
  /** true = 同区域内；false = 需要跨区域 */
  same_region: boolean
  region_name: string
}

/** 场景（Hub 当前地点，两级：区域 → 地点） */
export interface HubScene {
  id: string
  name: string
  region_name: string
  desc: string
  can_sleep: boolean
  /** 当前地点的背景 id（后端按 scenes.yaml 的 background 解析） */
  background: string | null
  /** 本地点的商店（没有则为 null） */
  shop: { id: string; name: string } | null
  adjacent: SceneLink[]
}

/** 背包物品 */
export interface InventoryItem {
  id: string
  name: string
  count: number
  gift_value: number
  desc: string
  /** 卖出单价（商店回收价） */
  sell_price: number
  /** 分类：item / equip / skill / key */
  category: string
  category_label: string
  /** 是否可使用 */
  usable: boolean
}

/** 商店商品 */
export interface ShopGood {
  id: string
  name: string
  price: number
  gift_value: number
  desc: string
  affordable: boolean
}

/** 角色一览/详情数据（后端 characters.list） */
export interface CharacterInfo {
  char_id: string
  name: string
  title: string
  tags: string[]
  relation: number
  /** 关系阶段：explicit=true 表示由突破事件设定，否则按好感度自动推算 */
  relation_stage: { label: string; key: string; explicit: boolean; auto_label: string }
  location: string
  stats: Record<string, number>
  flags: Record<string, unknown>
  /** 自定义能力（剧本 data.define_stat 注册） */
  extra: Record<string, unknown>
  extra_labels: Record<string, string>
  /** 互动历史，最近的在前 */
  history: { day: number; title: string; changes: string }[]
}

/** 角色一览排序方式 */
export type CharSort = 'relation' | 'name' | 'stage' | 'location'

export interface InputRequest {
  requestId: string
  prompt: string
  default: string
  maxLength: number
}

interface GameState {
  uiMode: UiMode
  /** 覆盖层实例（P3 Overlay Host）：独立 UI 模块，覆盖在根界面上，不改 uiMode */
  overlay: OverlayInstance | null
  /** UI 状态转移环形缓冲（最近 200 条；window.__eteraUiLog 可导出） */
  uiTransitions: UiTransition[]
  /** 根界面代际：根切换 +1，用于丢弃过期的异步结果 */
  uiEpoch: number
  /** 读档请求发起时的代际（null = 没有待处理读档） */
  pendingLoadEpoch: number | null
  /** 当前等待结束信号的剧本事件；用于丢弃旧事件的迟到 event.done */
  pendingEvent: { name: string; epoch: number } | null
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
  /** 文本区是否空闲（无打印、无待确认段落）——选项/输入框只在空闲时出现 */
  textIdle: boolean
  /** 文本推进信号（GameScreen 点击委托递增，TextFlow 监听推进段落） */
  textAdvanceTick: number
  /** 自动播放模式：选择选项/提交输入/小游戏结束后，新对话自动连续显示（直到下一交互点） */
  autoAdvance: boolean
  /** 读档重放中：TextFlow 直接把快照全文显示，不走逐字打印 */
  restoring: boolean
  /** Hub：角色卡片 */
  hubCharacters: HubCharacter[]
  /** Hub：剧本注册的行动按钮 */
  hubButtons: HubButton[]
  /** Hub：当前选中的角色（null = 未选） */
  hubSelectedChar: string | null
  /** 当前事件是否已播完（用于提示"可以返回了"） */
  eventFinished: boolean
  /**
   * 悬浮系统面板：覆盖在当前界面之上，不切换 uiMode。
   * 用 uiMode 切换会把整个页面替换掉（SaveScreen 渲染在 GameScreen 内），
   * 离开叙事页后就只剩空壳 —— 表现为"点保存后跳到一个只有 —— 的页面"。
   */
  panel: 'save' | 'load' | 'settings' | 'characters' | 'shop' | 'gift' | 'inventory' | null
  /** 角色一览数据 */
  charactersList: CharacterInfo[]
  /** 角色一览排序方式 */
  charSort: CharSort
  /** 正在查看详情的角色 ID（null = 未打开详情） */
  detailChar: string | null
  /** Hub 当前场景 */
  hubScene: HubScene | null
  /** 当前商店信息（null = 没有商店） */
  shopInfo: { id: string; name: string } | null
  /** 商店商品 */
  shopGoods: ShopGood[]
  /** 送礼目标角色（null = 未打开送礼面板） */
  giftChar: string | null
  /** 背包（送礼面板用） */
  inventory: InventoryItem[]
  /** 商店面板页签：买入 / 卖出 */
  shopTab: 'buy' | 'sell'
  /** 全屏 CG（null = 普通叙事画面） */
  cgImage: string | null
  /** 背包分类筛选 */
  invCategory: 'all' | 'item' | 'equip' | 'skill' | 'key'
}

const DEFAULT_WS = `ws://127.0.0.1:${WS_PORT}`

export const useGameStore = defineStore('game', {
  state: (): GameState => ({
    uiMode: 'main_menu',
    overlay: null,
    uiTransitions: [],
    uiEpoch: 0,
    pendingLoadEpoch: null,
    pendingEvent: null,
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
    textIdle: true,
    textAdvanceTick: 0,
    autoAdvance: false,
    restoring: false,
    hubCharacters: [],
    hubButtons: [],
    hubSelectedChar: null,
    eventFinished: false,
    panel: null,
    charactersList: [],
    charSort: 'relation',
    detailChar: null,
    hubScene: null,
    shopInfo: null,
    shopGoods: [],
    giftChar: null,
    inventory: [],
    shopTab: 'buy',
    cgImage: null,
    invCategory: 'all',
  }),

  getters: {
    /**
     * 存读档是否可用 —— 只在脚本空闲时允许。
     *
     * 原因：存档只序列化后端 GameContext，对话文本/立绘/选项都在前端，
     * 中途存档会存出"数据在前、画面在半截"的不一致档。所以要求
     * 无选项/输入/小游戏等待，且文本已播完（textIdle）才能存读档。
     */
    /** Hub 中当前选中角色的行动按钮（按 order 排序） */
    hubCharButtons(state): HubButton[] {
      if (!state.hubSelectedChar) return []
      return state.hubButtons
        .filter((b) => b.char === state.hubSelectedChar)
        .sort((a, b) => a.order - b.order)
    },

    /** 按当前排序方式排好的角色列表 */
    sortedCharacters(state): CharacterInfo[] {
      const list = [...state.charactersList]
      const byName = (a: CharacterInfo, b: CharacterInfo) => a.name.localeCompare(b.name, 'zh')
      switch (state.charSort) {
        case 'name':
          return list.sort(byName)
        case 'stage':
          // 关系阶段高→低，同阶段按好感
          return list.sort((a, b) => b.relation - a.relation)
        case 'location':
          return list.sort(
            (a, b) => a.location.localeCompare(b.location, 'zh') || byName(a, b),
          )
        case 'relation':
        default:
          return list.sort((a, b) => b.relation - a.relation)
      }
    },

    /** 当前查看详情的角色数据 */
    detailCharacter(state): CharacterInfo | null {
      if (!state.detailChar) return null
      return state.charactersList.find((c) => c.char_id === state.detailChar) ?? null
    },

    /** 按分类筛选后的背包（背包面板用） */
    filteredInventory(state): InventoryItem[] {
      if (state.invCategory === 'all') return state.inventory
      return state.inventory.filter((it) => it.category === state.invCategory)
    },

    canPersist(state): boolean {
      return state.choice === null
        && state.input === null
        && state.overlay === null
        && state.textIdle
    },
  },

  actions: {
    /**
     * 建立 WS 连接并注册协议处理器。
     *
     * 幂等：HMR 或组件重复挂载会多次调用本方法。若不清理，每次都会注册一批
     * 新闭包 → handler 累积 → 同一条消息被处理多次（文本重复、选项错乱）。
     * 因此：先清空旧 handler 再重绑；连接已存在则直接复用（避免重连导致
     * 后端新建引擎、游戏状态被重置）。
     */
    connect(): void {
      wsClient.clearHandlers()
      this.bindHandlers()

      if (wsClient.isConnected) {
        this.connected = true
        wsClient.send({ type: 'game.list_saves' })
        return
      }

      wsClient.connect(this.wsUrl).then(() => {
        this.connected = true
        // 拉取存档列表（主菜单"继续游戏"可用性判断）
        wsClient.send({ type: 'game.list_saves' })
      }).catch((e) => {
        console.error('[store] 连接失败', e)
        this.connected = false
      })
    },

    /** 注册全部 WS 消息处理器（与连接解耦，便于幂等重绑） */
    bindHandlers(): void {
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
        this.autoAdvance = false // 进入交互等待
      })
      wsClient.on('ui.ask_input', (m) => {
        const p = (m.payload ?? {}) as { prompt?: string; default?: string; max_length?: number }
        this.input = {
          requestId: m.requestId ?? '',
          prompt: p.prompt ?? '',
          default: p.default ?? '',
          maxLength: p.max_length ?? 100,
        }
        this.autoAdvance = false
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
        const p = (m.payload ?? {}) as { ok?: boolean; slot_id?: number; reason?: string | null }
        this.showToast(p.ok ? `已保存到槽位 ${p.slot_id}` : (p.reason ?? '保存失败'))
      })
      wsClient.on('load.result', (m) => {
        const p = (m.payload ?? {}) as {
          ok?: boolean
          reason?: string | null
          dialogue?: unknown[]
        }
        // 读档是异步的：期间若已回到主菜单/换了界面，结果必须丢弃
        const stale = this.pendingLoadEpoch === null || this.pendingLoadEpoch !== this.uiEpoch
        this.pendingLoadEpoch = null
        if (stale) {
          this.logIgnored('load.result', p.reason ?? undefined)
          return
        }
        if (p.ok) {
          this.showToast('读档成功')
          // 读档结束 = 面板使命完成，不能让它盖在新界面上
          this.panel = null
          this.detailChar = null
          const dialogue = Array.isArray(p.dialogue) ? p.dialogue : []
          if (dialogue.length > 0) {
            // 存档在叙事界面：重放当时那屏对话
            this.restoreDialogue(dialogue)
            this.resetMode('game', 'ws', 'load-dialogue')
          } else {
            // 存档在 Hub（没有对话）：直接回 Hub，别停在空的 —— 页面
            this.enterHub('ws', 'load-empty')
          }
        } else {
          this.showToast(p.reason ?? '读档失败')
        }
      })
      // 背包
      wsClient.on('inventory.data', (m) => {
        const p = (m.payload ?? {}) as { items?: InventoryItem[] }
        this.inventory = p.items ?? []
      })

      // 商店商品
      wsClient.on('shop.data', (m) => {
        const p = (m.payload ?? {}) as {
          ok?: boolean
          reason?: string
          shop?: { id: string; name: string }
          goods?: ShopGood[]
        }
        if (!p.ok) {
          this.showToast(p.reason ?? '这里没有商店')
          this.panel = null
          return
        }
        this.shopInfo = p.shop ?? null
        this.shopGoods = p.goods ?? []
      })

      // 卖出结果
      wsClient.on('sell.result', (m) => {
        const p = (m.payload ?? {}) as {
          ok?: boolean; item?: string; income?: number; reason?: string
        }
        if (p.ok) {
          this.showToast(`卖出 ${p.item}（+${p.income} 文）`)
          this.refreshInventory()
          // 钱变了 → 重新拉一次商品，让「买入」按钮的可买状态立即更新
          if (this.panel === 'shop') wsClient.send({ type: 'game.shop' })
        } else {
          this.showToast(p.reason ?? '卖不出去')
        }
      })

      // 购买结果
      wsClient.on('buy.result', (m) => {
        const p = (m.payload ?? {}) as {
          ok?: boolean; item?: string; count?: number; cost?: number; reason?: string
        }
        if (p.ok) {
          this.showToast(`买了 ${p.item} ×${p.count}（-${p.cost} 文）`)
          wsClient.send({ type: 'game.shop' })   // 刷新价格可买状态
        } else {
          this.showToast(p.reason ?? '购买失败')
        }
      })

      // 送礼结果
      wsClient.on('gift.result', (m) => {
        const p = (m.payload ?? {}) as {
          ok?: boolean; item?: string; gain?: number; relation?: number
          liked?: boolean; reason?: string
        }
        if (p.ok) {
          const liked = p.liked ? "（对方很喜欢！）" : ""
          this.showToast(`送出 ${p.item}，好感 +${p.gain}${liked}（现在 ${p.relation}）`)
          this.panel = null
          this.giftChar = null
        } else {
          this.showToast(p.reason ?? '送礼失败')
        }
      })

      // 移动结果
      wsClient.on('move.result', (m) => {
        const p = (m.payload ?? {}) as { ok?: boolean; reason?: string | null; name?: string }
        if (p.ok) {
          this.showToast(`来到 ${p.name ?? ''}`)
          this.hubSelectedChar = null
        } else {
          this.showToast(p.reason ?? '无法移动')
        }
      })

      // 睡觉结果
      wsClient.on('sleep.result', (m) => {
        const p = (m.payload ?? {}) as { ok?: boolean; reason?: string | null }
        if (p.ok) {
          // 睡觉只从 Hub 发起；若结果迟到而玩家已回主菜单，不能把界面拽进空游戏页
          if (this.uiMode !== 'hub') {
            this.logIgnored('sleep.result')
            return
          }
          this.showToast('睡了一觉，体力恢复了')
          this.hubSelectedChar = null
          // 新的一天可能有早晨事件（会弹对话/选项）—— 必须切到叙事界面，
          // 否则 Hub 不渲染 ChoiceMenu，选项"消失"而脚本一直挂着。
          this.textFlow = []
          this.choice = null
          this.input = null
          this.characters.clear()
          this.eventFinished = false
          this.autoAdvance = true
          this.resetMode('game', 'ws', 'sleep')
          // 睡觉后的 on_day_begin 结束信号沿用 day_advance
          this.pendingEvent = { name: 'day_advance', epoch: this.uiEpoch }
        } else {
          this.showToast(p.reason ?? '睡不着')
        }
      })

      // 推进一天的结果
      wsClient.on('day.result', (m) => {
        const p = (m.payload ?? {}) as { ok?: boolean; reason?: string | null }
        if (!p.ok) this.showToast(p.reason ?? '推进失败')
      })
      // 手动触发事件的结果（Hub 行动 / 工具条「自检」等）
      wsClient.on('event.result', (m) => {
        const p = (m.payload ?? {}) as { ok?: boolean; reason?: string | null; event?: string }
        if (p.ok) return
        this.showToast(p.reason ?? '触发失败')
        // Hub 行动被后端拒绝时，chooseHubButton 已切到 game 并清空内容；
        // 若不回收，就会永久停在没有文字/选项的空壳上。
        if (this.uiMode === 'game'
            && this.textFlow.length === 0
            && !this.choice
            && !this.input
            && !this.overlay) {
          this.enterHub('ws', 'event-rejected')
        }
      })
      // 角色一览/详情数据
      wsClient.on('characters.list', (m) => {
        const p = (m.payload ?? {}) as { characters?: CharacterInfo[] }
        this.charactersList = p.characters ?? []
      })

      // Hub 数据：角色卡片 + 剧本注册的行动按钮
      wsClient.on('hub.buttons', (m) => {
        const p = (m.payload ?? {}) as {
          scene?: HubScene
          characters?: HubCharacter[]
          buttons?: HubButton[]
        }
        this.hubScene = p.scene ?? null
        this.hubCharacters = p.characters ?? []
        this.hubButtons = p.buttons ?? []
        // Hub 也显示地点背景：进入/移动后立即同步（移动时后端还会先推 ui.background_set）
        if (this.uiMode === 'hub' && p.scene?.background) {
          this.background = p.scene.background
        }
        // 选中角色若已不在列表里则清空
        if (this.hubSelectedChar
            && !this.hubCharacters.some((c) => c.char_id === this.hubSelectedChar)) {
          this.hubSelectedChar = null
        }
      })

      // 剧本播完：只标记状态，不自动切界面。
      // 由玩家点击（点击委托 → TextFlow.onAdvance）确认后回 Hub。
      wsClient.on('event.done', (m) => {
        // 只处理当前叙事界面的结束信号。玩家已回主菜单/Hub 后又收到迟到的
        // event.done（abort 后脚本 finally 仍会发），不能再改界面。
        if (this.uiMode !== 'game') {
          this.logIgnored('event.done')
          return
        }
        // 只接受“当前在等”的那个事件：旧事件的 done 不能结束新事件。
        const p = (m.payload ?? {}) as { event?: string }
        const name = p.event ?? ''
        const pending = this.pendingEvent
        if (!pending
            || pending.epoch !== this.uiEpoch
            || (name && pending.name !== name)) {
          this.logIgnored(
            'event.done',
            `${name || '?'} (waiting ${pending?.name ?? 'none'})`,
          )
          return
        }
        this.pendingEvent = null
        this.eventFinished = true
        // 本段没有产生任何对话（例如睡觉后当天没有日常事件）→ 不必停在空界面
        if (!this.textFlow.length) {
          this.enterHub('ws', 'event-done-empty')
        }
      })

      // 全屏 CG 特写（DSL ui.cg / ui.cg_off）
      wsClient.on('ui.cg', (m) => {
        const p = (m.payload ?? {}) as { name?: string | null }
        this.cgImage = p.name ?? null
      })

      // 使用物品结果
      wsClient.on('use.result', (m) => {
        const p = (m.payload ?? {}) as {
          ok?: boolean; name?: string; changes?: string; reason?: string
        }
        if (p.ok) {
          this.showToast(`用了 ${p.name}：${p.changes}`)
          this.refreshInventory()
        } else {
          this.showToast(p.reason ?? '用不了')
        }
      })

      // 小游戏触发（DSL minigame.start）：打开覆盖层，根界面保持不动
      wsClient.on('minigame.start', (m) => {
        // 只允许从叙事界面进入；迟到的启动消息不能把主菜单顶掉
        if (this.uiMode !== 'game' || this.overlay) {
          this.logIgnored('minigame.start')
          return
        }
        const p = (m.payload ?? {}) as { game_id?: string }
        this.openOverlay(
          'minigame',
          { gameId: p.game_id ?? '' },
          m.requestId ?? null,
          'ws',
          'minigame-start',
        )
        this.autoAdvance = false
      })
    },

    /**
     * 读档重放：用存档里的对话快照还原画面（文本/背景/立绘）。
     *
     * 存档只序列化服务端 GameContext，画面本在前端；不重放就会出现
     * "数据回来了、文本区只剩 ——"的空屏。重放期间置 restoring=true，
     * TextFlow 会把快照全文直接铺满，不再逐字重播一遍。
     */
    restoreDialogue(entries: unknown[]): void {
      this.restoring = true
      this.choice = null
      this.input = null
      this.textFlow = []
      this.background = null
      this.characters.clear()

      for (const raw of entries) {
        const e = raw as { type?: string; payload?: Record<string, unknown> }
        const p = e?.payload ?? {}
        switch (e?.type) {
          case 'ui.clear':
            this.textFlow = []
            this.background = null
            this.characters.clear()
            break
          case 'ui.text':
            this.textFlow.push({
              text: String(p.text ?? ''),
              color: (p.color as string | null | undefined) ?? null,
              bold: Boolean(p.bold),
            })
            break
          case 'ui.background_set':
            this.background = String(p.name ?? '')
            break
          case 'ui.character_show':
            this.characters.set(String(p.char_id ?? ''), {
              charId: String(p.char_id ?? ''),
              expression: String(p.expression ?? 'normal'),
              position: String(p.position ?? 'center'),
            })
            break
          case 'ui.character_hide':
            this.characters.delete(String(p.char_id ?? ''))
            break
          default:
            break
        }
      }

      // 放开 restoring：TextFlow 在 watch 里已按快照全文渲染
      nextTick(() => {
        this.restoring = false
      })
    },

    showToast(message: string): void {
      this.toast = message
      setTimeout(() => {
        this.toast = null
      }, 2200)
    },

    /** 写入一条 UI 转移日志（根切换与覆盖层共用） */
    recordTransition(entry: UiTransition): void {
      this.uiTransitions.push(entry)
      if (this.uiTransitions.length > UI_LOG_LIMIT) {
        this.uiTransitions.splice(0, this.uiTransitions.length - UI_LOG_LIMIT)
      }
      if (typeof window !== 'undefined') {
        ;(window as unknown as Record<string, unknown>).__eteraUiLog = this.uiTransitions
      }
      if (uiDebugEnabled()) console.debug('[ui.transition]', entry)
    },

    /** 当前内容的摘要（用于日志取证） */
    contentSnapshot(): UiTransition['content'] {
      return {
        texts: this.textFlow.length,
        choices: this.choice?.options.length ?? 0,
        hasInput: this.input !== null,
        background: this.background,
        characters: this.characters.size,
        panel: this.panel,
        overlay: this.overlay?.moduleId ?? null,
      }
    },

    /** 根界面切换：作废待处理读档/事件，代际 +1 */
    transitionTo(
      mode: BaseMode,
      source: UiTransitionSource,
      reason?: string,
    ): void {
      const fromMode = this.uiMode
      this.uiMode = mode
      this.recordTransition({
        time: new Date().toISOString(),
        action: 'reset',
        source,
        fromMode,
        toMode: mode,
        overlay: this.overlay
          ? { id: this.overlay.id, moduleId: this.overlay.moduleId }
          : null,
        reason,
        content: this.contentSnapshot(),
      })
    },

    /** 记录被丢弃的迟到消息（默认只在调试模式打印） */
    logIgnored(kind: string, detail?: string): void {
      if (uiDebugEnabled()) console.debug('[ui] ignored stale message:', kind, detail ?? '')
    },

    /** 根界面切换：清空待处理读档/事件、代际 +1、不改变覆盖层 */
    resetMode(
      mode: BaseMode,
      source: UiTransitionSource = 'system',
      reason?: string,
    ): void {
      this.uiEpoch++
      this.pendingLoadEpoch = null
      this.pendingEvent = null
      this.transitionTo(mode, source, reason)
    },

    /**
     * 打开覆盖层模块（P3 Overlay Host）。
     * 同一时间只允许一个覆盖层；重复打开直接忽略，避免叠层。
     */
    openOverlay(
      moduleId: string,
      input: Record<string, unknown>,
      requestId: string | null,
      source: UiTransitionSource = 'user',
      reason?: string,
    ): OverlayInstance | null {
      if (this.overlay) {
        console.warn('[ui] 已有覆盖层，忽略重复打开:', moduleId)
        return null
      }
      const overlay: OverlayInstance = {
        id: `overlay-${++overlaySeq}`,
        moduleId,
        input,
        requestId,
      }
      this.overlay = overlay
      this.recordTransition({
        time: new Date().toISOString(),
        action: 'overlay-open',
        source,
        fromMode: this.uiMode,
        toMode: this.uiMode,
        overlay: { id: overlay.id, moduleId: overlay.moduleId },
        reason,
        content: this.contentSnapshot(),
      })
      return overlay
    },

    /**
     * 结束覆盖层并（若由 DSL 触发）回传结果。
     * 幂等：第一次结束后 overlay 清空，重复调用直接忽略。
     */
    completeOverlay(
      result: Record<string, unknown>,
      status: OverlayStatus = 'completed',
      source: UiTransitionSource = 'user',
      instanceId?: string,
    ): void {
      const overlay = this.overlay
      if (!overlay || (instanceId && overlay.id !== instanceId)) {
        this.logIgnored('completeOverlay', instanceId)
        return
      }
      const finalStatus: OverlayStatus =
        status === 'completed' && result.cancelled === true ? 'cancelled' : status
      this.overlay = null
      this.recordTransition({
        time: new Date().toISOString(),
        action: 'overlay-close',
        source,
        fromMode: this.uiMode,
        toMode: this.uiMode,
        overlay: { id: overlay.id, moduleId: overlay.moduleId },
        reason: finalStatus,
        content: this.contentSnapshot(),
      })

      if (overlay.requestId) {
        const payloadResult = finalStatus === 'cancelled'
          ? { ...result, cancelled: true }
          : result
        wsClient.send({
          type: 'minigame.result',
          requestId: overlay.requestId,
          payload: { result: payloadResult },
        })
      } else if (finalStatus === 'completed') {
        this.showToast(result.won ? '小游戏胜利！' : '小游戏结束')
      }
      this.autoAdvance = true
    },

    /** 取消当前覆盖层（DSL 触发时回传 cancelled） */
    cancelOverlay(
      source: UiTransitionSource = 'user',
      reason = 'cancel',
      instanceId?: string,
    ): void {
      if (!this.overlay || (instanceId && this.overlay.id !== instanceId)) {
        this.logIgnored('cancelOverlay', instanceId)
        return
      }
      this.completeOverlay({ cancelled: true }, 'cancelled', source, instanceId)
      if (uiDebugEnabled()) console.debug('[ui] overlay cancelled:', reason)
    },

    /** 静默清理覆盖层（重启/回 Hub/回主菜单时；不发结果，脚本会被 abort） */
    clearOverlay(source: UiTransitionSource, reason: string): void {
      const overlay = this.overlay
      if (!overlay) return
      this.overlay = null
      this.recordTransition({
        time: new Date().toISOString(),
        action: 'overlay-close',
        source,
        fromMode: this.uiMode,
        toMode: this.uiMode,
        overlay: { id: overlay.id, moduleId: overlay.moduleId },
        reason,
        content: this.contentSnapshot(),
      })
    },

    /** 开始新游戏 */
    startGame(): void {
      this.clearOverlay('user', 'start-game')
      this.resetMode('game', 'user', 'start-game')
      this.textFlow = []
      this.choice = null
      this.input = null
      this.background = null
      this.cgImage = null
      this.characters.clear()
      this.panel = null
      this.detailChar = null
      this.eventFinished = false
      this.pendingEvent = { name: 'on_game_start', epoch: this.uiEpoch }
      wsClient.send({ type: 'game.start' })
    },

    /** 返回主菜单（清内容/覆盖层 + 通知后端中止挂起脚本，释放游戏线程） */
    backToMenu(): void {
      this.clearOverlay('user', 'back-to-menu')
      this.resetMode('main_menu', 'user', 'back-to-menu')
      this.textFlow = []
      this.choice = null
      this.input = null
      this.background = null
      this.cgImage = null
      this.characters.clear()
      this.panel = null
      this.detailChar = null
      this.giftChar = null
      this.hubSelectedChar = null
      this.autoAdvance = false
      this.eventFinished = false
      wsClient.send({ type: 'game.abort' })
    },

    /** ── 存档界面（模式栈：save/load）────────────────── */
    /** 打开角色一览浮窗 */
    openCharacters(): void {
      this.panel = 'characters'
      this.detailChar = null
      wsClient.send({ type: 'game.characters' })
    },

    /** 关闭角色一览（连详情一起关） */
    closeCharacters(): void {
      this.detailChar = null
      this.panel = null
    },

    /** 切换排序方式 */
    setCharSort(sort: CharSort): void {
      this.charSort = sort
    },

    /** 进入某角色的详情页 */
    openCharDetail(charId: string): void {
      this.detailChar = charId
    },

    /** 从详情返回列表 */
    closeCharDetail(): void {
      this.detailChar = null
    },

    openSave(): void {
      this.panel = 'save'
      wsClient.send({ type: 'game.list_saves' })
    },

    openLoad(): void {
      this.panel = 'load'
      wsClient.send({ type: 'game.list_saves' })
    },

    closeMenu(): void {
      // 关悬浮面板，回到原界面（uiMode 从未改变）
      this.panel = null
    },

    /** 打开背包 */
    openInventory(): void {
      this.panel = 'inventory'
      this.invCategory = 'all'
      this.refreshInventory()
    },

    /** 切换背包分类 */
    setInvCategory(cat: 'all' | 'item' | 'equip' | 'skill' | 'key'): void {
      this.invCategory = cat
    },

    /** 使用物品 */
    useItem(itemId: string): void {
      wsClient.send({ type: 'game.use_item', payload: { item: itemId } })
    },

    /** 打开当前地点的商店 */
    openShop(): void {
      this.panel = 'shop'
      this.shopTab = 'buy'
      wsClient.send({ type: 'game.shop' })
    },

    /** 购买商品 */
    buyItem(itemId: string): void {
      wsClient.send({ type: 'game.buy', payload: { item: itemId, count: 1 } })
    },

    /** 打开送礼面板（对指定角色）：先进浮窗，背包由 GiftModal 拉取 */
    openGift(charId: string): void {
      this.giftChar = charId
      this.panel = 'gift'
      this.refreshInventory()
    },

    /** 刷新背包 */
    refreshInventory(): void {
      wsClient.send({ type: 'game.inventory' })
    },

    /** 送出物品 */
    sendGift(itemId: string): void {
      if (!this.giftChar) return
      wsClient.send({
        type: 'game.gift',
        payload: { char: this.giftChar, item: itemId },
      })
    },

    /** 回家：无视相邻规则直接回自宅 */
    goHome(): void {
      wsClient.send({ type: 'game.home' })
    },

    /** 切换商店页签（买入/卖出） */
    setShopTab(tab: 'buy' | 'sell'): void {
      this.shopTab = tab
      if (tab === 'sell') this.refreshInventory()
    },

    /** 卖出背包物品 */
    sellItem(itemId: string): void {
      wsClient.send({ type: 'game.sell', payload: { item: itemId, count: 1 } })
    },

    /** 移动到相邻场景 */
    moveTo(sceneId: string): void {
      wsClient.send({ type: 'game.move', payload: { scene: sceneId } })
    },

    /** 睡觉：恢复体力并推进一天（仅当前场景允许时可用） */
    doSleep(): void {
      if (!this.hubScene?.can_sleep) {
        this.showToast('这里睡不着')
        return
      }
      wsClient.send({ type: 'game.sleep' })
    },

    /** 进入 Hub（行动枢纽）：清空叙事区、拉取按钮列表 */
    enterHub(
      source: UiTransitionSource = 'user',
      reason = 'enter-hub',
    ): void {
      this.clearOverlay(source, 'enter-hub')
      this.resetMode('hub', source, reason)
      this.textFlow = []
      this.choice = null
      this.input = null
      this.eventFinished = false
      this.cgImage = null
      this.characters.clear()
      this.panel = null
      this.detailChar = null
      this.giftChar = null
      this.shopInfo = null
      this.shopGoods = []
      this.autoAdvance = false
      // 关键：中止可能仍挂起的脚本。
      // 玩家从对话中途点「返回」时，后端脚本还等在 ask_choice 上，
      // 不中止的话后续所有操作都会被 "对话进行中" 挡住。
      wsClient.send({ type: 'game.abort' })
      // 后端在 game.hub 时会清空对话快照：Hub 里存档 = 无对话可恢复
      wsClient.send({ type: 'game.hub' })
    },

    /** 选中/取消选中某个角色（Hub 角色卡片） */
    selectHubChar(charId: string): void {
      this.hubSelectedChar = this.hubSelectedChar === charId ? null : charId
    },

    /** 点 Hub 上的角色行动按钮 → 播对应剧本 */
    chooseHubButton(btn: HubButton): void {
      if (!btn.available) {
        this.showToast(btn.reason ?? '该行动当前不可用')
        return
      }
      this.autoAdvance = true      // 事件内对话连续播放，不用一段一点
      this.eventFinished = false
      // 新事件是独立场景：清掉上一段的文本/背景/立绘，避免累积成一团
      this.resetMode('game', 'user', 'hub-action')
      this.textFlow = []
      this.choice = null
      this.input = null
      this.cgImage = null
      this.characters.clear()
      this.pendingEvent = { name: btn.event, epoch: this.uiEpoch }
      wsClient.send({ type: 'game.emit_event', payload: { event: btn.event } })
    },

    /** 工具条「下一天」：推进一天，触发 on_day_end → on_day_begin 日常事件 */
    advanceDay(): void {
      if (!this.canPersist) {
        this.showToast('对话进行中，请先完成当前对话')
        return
      }
      this.eventFinished = false
      // 新的一天：清掉前一天残留的文本/背景/立绘
      this.resetMode('game', 'user', 'day-advance')
      this.textFlow = []
      this.choice = null
      this.input = null
      this.characters.clear()
      this.pendingEvent = { name: 'day_advance', epoch: this.uiEpoch }
      wsClient.send({ type: 'game.day_advance' })
    },

    /** 工具条「自检」：触发 DSL 全指令自检剧本（custom:run_selftest） */
    runSelftest(): void {
      if (!this.canPersist) {
        this.showToast('对话进行中，请先完成当前对话')
        return
      }
      // 自检剧本会先弹选项；Hub 不渲染 ChoiceMenu，必须切到叙事界面
      this.resetMode('game', 'user', 'selftest')
      this.textFlow = []
      this.choice = null
      this.input = null
      this.cgImage = null
      this.characters.clear()
      this.eventFinished = false
      this.autoAdvance = true
      this.pendingEvent = { name: 'custom:run_selftest', epoch: this.uiEpoch }
      wsClient.send({
        type: 'game.emit_event',
        payload: { event: 'custom:run_selftest' },
      })
    },

    openSettings(): void {
      this.panel = 'settings'
    },

    openMinigame(): void {
      // 主菜单测试入口（无 requestId，结果不回传脚本）
      this.openOverlay(
        'minigame',
        { gameId: 'slime_battle' },
        null,
        'user',
        'minigame-test',
      )
    },

    /** 兼容旧调用：小游戏结束统一走 completeOverlay（幂等） */
    finishMinigame(result: Record<string, unknown>): void {
      this.completeOverlay(result, 'completed', 'user')
    },

    /** 兼容旧调用：小游戏取消统一走 cancelOverlay */
    cancelMinigame(): void {
      this.cancelOverlay('user', 'minigame-cancel')
    },

    saveToSlot(slotId: number): void {
      wsClient.send({
        type: 'game.save',
        payload: { slot_id: slotId, description: `第${this.status?.day ?? 1}天存档` },
      })
      this.panel = null      // 关面板，留在当前界面（Hub 或叙事）
    },

    quickSave(): void {
      wsClient.send({ type: 'game.quick_save' })
    },

    loadFromSlot(slotId: number): void {
      // 目标界面由 load.result 决定（有对话快照→叙事，无→Hub）
      // 记录发起时的界面代际：迟到的结果不会覆盖后来切换的界面
      this.pendingLoadEpoch = this.uiEpoch
      wsClient.send({ type: 'game.load', payload: { slot_id: slotId } })
    },

    quickLoad(): void {
      this.pendingLoadEpoch = this.uiEpoch
      wsClient.send({ type: 'game.quick_load' })
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
      this.autoAdvance = true // 选择后对话自动连续播放
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
      this.autoAdvance = true
    },

    scrollToBottom(): void {
      // 由 TextFlow 组件通过 watch 处理滚动
    },
  },
})
