/**
 * WS 客户端 —— 协议见 docs/architecture.md §四
 * 引擎 → 前端：ui.* 指令（推送）
 * 前端 → 引擎：game.start / choice.made / input.submit
 */
export interface WsMessage {
  type: string
  requestId?: string
  payload?: Record<string, unknown>
}

type MessageHandler = (msg: WsMessage) => void

export class WsClient {
  private ws: WebSocket | null = null
  private handlers = new Map<string, Set<MessageHandler>>()
  private connected = false

  get isConnected(): boolean {
    return this.connected
  }

  connect(url: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url)
      this.ws = ws
      ws.onopen = () => {
        this.connected = true
        resolve()
      }
      ws.onerror = (ev) => {
        reject(new Error('WS 连接失败: ' + String(ev)))
      }
      ws.onclose = () => {
        this.connected = false
        this.dispatch({ type: '__connection_closed' })
      }
      ws.onmessage = (ev) => {
        try {
          this.dispatch(JSON.parse(ev.data as string) as WsMessage)
        } catch {
          console.warn('[ws] 非法消息', ev.data)
        }
      }
    })
  }

  /** 注册某类型消息处理器 */
  on(type: string, handler: MessageHandler): () => void {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set())
    this.handlers.get(type)!.add(handler)
    return () => this.handlers.get(type)?.delete(handler)
  }

  /**
   * 清空所有处理器。
   *
   * 用途：HMR / 组件重复挂载会让 store 的 connect() 被多次调用，而 on() 每次都
   * 传入新的闭包，Set 无法去重 → handler 累积，同一条消息会被处理 N 次
   * （表现：文本重复、选项被后续消息覆盖）。重绑前先清空可保证幂等。
   */
  clearHandlers(): void {
    this.handlers.clear()
  }

  /** 发送消息（未连接时丢弃并告警） */
  send(msg: WsMessage): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[ws] 未连接，消息丢弃', msg.type)
      return
    }
    this.ws.send(JSON.stringify(msg))
  }

  private dispatch(msg: WsMessage): void {
    this.handlers.get(msg.type)?.forEach((h) => {
      try {
        h(msg)
      } catch (e) {
        console.error('[ws] 处理器异常', msg.type, e)
      }
    })
  }
}

export const wsClient = new WsClient()
