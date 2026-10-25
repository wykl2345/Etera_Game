/**
 * 游戏状态 store —— 前端唯一状态源（视图在客户端，状态在服务端 ADR-0003）
 * 消息处理对应后端 ws_gateway 的推送。
 */
import { defineStore } from 'pinia'
import { nextTick } from 'vue'
import { wsClient } from '../ws/client'

/** 静态资源基地址（后端 main.py 的静态服务，默认 127.0.0.1:8766） */
export const ASSET_BASE = 'http://127.0.0.1:8766'

export type UiMode = 'main_menu' | 'hub' | 'game' | 'settings' | 'save' | 'load' | 'character_detail' | 'minigame'

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
}

/** 角色一览/详情数据（后端 characters.list） */
export interface CharacterInfo {
  char_id: string
  name: string
  title: string
  tags: string[]
  relation: number
  relation_stage: { label: string; key: string }
  location: string
  stats: Record<string, number>
  flags: Record<string, unknown>
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
  panel: 'save' | 'load' | 'settings' | 'characters' | null
  /** 角色一览数据 */
  charactersList: CharacterInfo[]
  /** 角色一览排序方式 */
  charSort: CharSort
  /** 正在查看详情的角色 ID（null = 未打开详情） */
  detailChar: string | null
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

    canPersist(state): boolean {
      return state.choice === null
        && state.input === null
        && state.activeMinigame === null
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
        if (p.ok) {
          this.showToast('读档成功')
          const dialogue = Array.isArray(p.dialogue) ? p.dialogue : []
          if (dialogue.length > 0) {
            // 存档在叙事界面：重放当时那屏对话
            this.restoreDialogue(dialogue)
            this.uiMode = 'game'
          } else {
            // 存档在 Hub（没有对话）：直接回 Hub，别停在空的 —— 页面
            this.modeStack = []
            this.enterHub()
          }
        } else {
          this.showToast(p.reason ?? '读档失败')
        }
      })
      // 推进一天的结果
      wsClient.on('day.result', (m) => {
        const p = (m.payload ?? {}) as { ok?: boolean; reason?: string | null }
        if (!p.ok) this.showToast(p.reason ?? '推进失败')
      })
      // 手动触发事件的结果（工具条「自检」等）
      wsClient.on('event.result', (m) => {
        const p = (m.payload ?? {}) as { ok?: boolean; reason?: string | null; event?: string }
        if (!p.ok) this.showToast(p.reason ?? '触发失败')
      })
      // 角色一览/详情数据
      wsClient.on('characters.list', (m) => {
        const p = (m.payload ?? {}) as { characters?: CharacterInfo[] }
        this.charactersList = p.characters ?? []
      })

      // Hub 数据：角色卡片 + 剧本注册的行动按钮
      wsClient.on('hub.buttons', (m) => {
        const p = (m.payload ?? {}) as {
          characters?: HubCharacter[]
          buttons?: HubButton[]
        }
        this.hubCharacters = p.characters ?? []
        this.hubButtons = p.buttons ?? []
        // 选中角色若已不在列表里则清空
        if (this.hubSelectedChar
            && !this.hubCharacters.some((c) => c.char_id === this.hubSelectedChar)) {
          this.hubSelectedChar = null
        }
      })

      // 剧本播完 → 等最后一段文本播完，自动回 Hub（不用玩家按返回）
      wsClient.on('event.done', () => {
        this.eventFinished = true
        this.scheduleHubReturn()
      })

      // 小游戏触发（DSL minigame.start）：进入 minigame 模式
      wsClient.on('minigame.start', (m) => {
        const p = (m.payload ?? {}) as { game_id?: string }
        this.pushMode('minigame')
        this.activeMinigame = { gameId: p.game_id ?? '', requestId: m.requestId ?? null }
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

    /**
     * 剧本播完后自动回 Hub。
     *
     * 不能立刻切：逐字打印比后端慢，剧本结束时前端可能还在播最后一段。
     * 所以轮询等 textIdle（无打印、无待确认段落），并额外停留 1s 让玩家看完。
     */
    scheduleHubReturn(): void {
      let waited = 0
      const tick = () => {
        if (this.uiMode !== 'game') return        // 玩家已手动离开
        if (this.textIdle && waited >= 1000) {
          this.enterHub()
          return
        }
        waited += 250
        if (waited > 20000) {                     // 兜底：20s 后强制回
          this.enterHub()
          return
        }
        setTimeout(tick, 250)
      }
      setTimeout(tick, 250)
    },

    /** 进入 Hub（行动枢纽）：清空叙事区、拉取按钮列表 */
    enterHub(): void {
      this.choice = null
      this.input = null
      this.activeMinigame = null
      this.eventFinished = false
      this.uiMode = 'hub'
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
      this.textFlow = []
      this.choice = null
      this.input = null
      this.background = null
      this.characters.clear()
      this.uiMode = 'game'
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
      this.textFlow = []
      this.choice = null
      this.input = null
      this.background = null
      this.characters.clear()
      this.uiMode = 'game'
      wsClient.send({ type: 'game.day_advance' })
    },

    /** 工具条「自检」：触发 DSL 全指令自检剧本（custom:run_selftest） */
    runSelftest(): void {
      if (!this.canPersist) {
        this.showToast('对话进行中，请先完成当前对话')
        return
      }
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
      this.autoAdvance = true // 小游戏结束后对话自动播放
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
      wsClient.send({ type: 'game.load', payload: { slot_id: slotId } })
    },

    quickLoad(): void {
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
