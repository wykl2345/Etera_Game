// Etera_Game 前后端联调验收脚本（模拟浏览器 WS 行为）
// 流程：game.start → 序章挂起 → choice.made(2) → 收结尾文本 → day_advance 验证日常事件机制
const WS_URL = 'ws://127.0.0.1:8799'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function run() {
  const ws = new WebSocket(WS_URL)
  const messages = []
  let askChoice = null

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data)
    messages.push(msg)
    if (msg.type === 'ui.ask_choice') askChoice = msg
  }

  await new Promise((resolve, reject) => {
    ws.onopen = resolve
    ws.onerror = reject
  })
  console.log('✓ 已连接', WS_URL)

  // 1. 开始新游戏
  ws.send(JSON.stringify({ type: 'game.start' }))
  console.log('✓ 发送 game.start，等待序章挂起…')

  // 等 ask_choice（序章含 1.5s sleep）
  const deadline = Date.now() + 8000
  while (!askChoice && Date.now() < deadline) await sleep(100)
  if (!askChoice) throw new Error('序章未发出选项')
  console.log('✓ 序章选项:', askChoice.payload.options.join(' | '))

  // 2. 选 2（在神社帮忙 → 好感+3）
  ws.send(JSON.stringify({
    type: 'choice.made',
    requestId: askChoice.requestId,
    payload: { index: 2 },
  }))
  console.log('✓ 选择「在神社帮忙」')
  await sleep(1500)
  const texts = messages.filter((m) => m.type === 'ui.text').map((m) => m.payload.text)
  const hasEnding = texts.some((t) => t.includes('新的旅程开始了'))
  const hasChara = messages.some((m) => m.type === 'ui.character_show')
  const hasBg = messages.some((m) => m.type === 'ui.background_set')
  console.log('✓ 序章完成:', hasEnding, '| 立绘:', hasChara, '| 背景:', hasBg)
  if (!hasEnding) throw new Error('序章未完成')

  // 3. day_advance 验证日常事件机制（on_day_begin）
  const before = messages.length
  for (let i = 0; i < 6; i++) {
    ws.send(JSON.stringify({ type: 'game.day_advance' }))
    await sleep(300)
  }
  await sleep(800)
  const newMsgs = messages.slice(before)
  const dailyChoice = newMsgs.find((m) => m.type === 'ui.ask_choice')
  console.log(`✓ day_advance×6 → 新消息 ${newMsgs.length} 条，日常事件选项: ${dailyChoice ? dailyChoice.payload.options.join(' | ') : '(未触发/随机未命中)'}`)

  // 4. 蘑菇事件如果触发则回应
  if (dailyChoice) {
    ws.send(JSON.stringify({
      type: 'choice.made',
      requestId: dailyChoice.requestId,
      payload: { index: 1 },
    }))
    await sleep(500)
    console.log('✓ 已回应日常事件选项')
  }

  ws.close()
  console.log('\n=== 联调验收通过 ===')
}

run().catch((e) => {
  console.error('✗ 联调失败:', e.message)
  process.exit(1)
})
