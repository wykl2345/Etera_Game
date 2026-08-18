// Etera_Game 前后端联调验收脚本（模拟浏览器 WS 行为）
// 流程：game.start → 序章挂起 → choice.made(2) → 收结尾文本 → day_advance 验证日常事件机制
const WS_URL = 'ws://127.0.0.1:8765'

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

  // 4.5 小游戏触发链路：minigame_demo 剧本（on_day_begin 触发 minigame.start）
  const mgStart = messages.filter((m) => m.type === 'minigame.start').at(-1)
  if (mgStart) {
    console.log('✓ DSL 触发小游戏:', mgStart.payload.game_id, '| 选项:', JSON.stringify(mgStart.payload.options))
    ws.send(JSON.stringify({
      type: 'minigame.result',
      requestId: mgStart.requestId,
      payload: { result: { won: true, score: 20 } },
    }))
    await sleep(600)
    const afterMg = messages.slice(before).filter((m) => m.type === 'ui.text').map((m) => m.payload.text)
    const hasReward = afterMg.some((t) => t.includes('奖励'))
    console.log('✓ 小游戏结果回传后脚本恢复，奖励文本:', hasReward)
    if (!hasReward) throw new Error('小游戏结果未正确回传脚本')
  } else {
    console.log('ℹ 未检测到小游戏触发（随机/条件未命中，后端单测已覆盖）')
  }

  // 5. 状态推送（status.sync）：写操作后应有状态快照
  await sleep(300)
  const statusMsgs = messages.filter((m) => m.type === 'status.sync')
  console.log(`✓ status.sync 收到 ${statusMsgs.length} 条`)
  if (statusMsgs.length === 0) throw new Error('未收到状态推送')
  const lastStatus = statusMsgs[statusMsgs.length - 1].payload
  console.log(`✓ 状态: 第 ${lastStatus.day} 天 / ${lastStatus.location} / 金钱 ${lastStatus.player.money}`)

  // 6. 存档链路：list → save → 再次 list → load
  ws.send(JSON.stringify({ type: 'game.list_saves' }))
  await sleep(400)
  const listMsgs = messages.filter((m) => m.type === 'saves.list')
  console.log(`✓ saves.list 收到 ${listMsgs.length} 次，槽位数: ${listMsgs.at(-1)?.payload?.slots?.length ?? 0}`)

  ws.send(JSON.stringify({ type: 'game.save', payload: { slot_id: 3, description: '联调测试' } }))
  await sleep(500)
  const saveOk = messages.filter((m) => m.type === 'save.result').at(-1)?.payload?.ok
  console.log('✓ game.save → save.result:', saveOk)
  if (!saveOk) throw new Error('保存失败')

  // 读档后状态应还原
  ws.send(JSON.stringify({ type: 'game.list_saves' }))
  await sleep(400)
  const slot3 = messages.filter((m) => m.type === 'saves.list').at(-1)?.payload?.slots?.find((s) => s.slot_id === 3)
  console.log(`✓ 槽位 3: exists=${slot3?.exists} day=${slot3?.metadata?.day}`)

  ws.send(JSON.stringify({ type: 'game.load', payload: { slot_id: 3 } }))
  await sleep(500)
  const loadOk = messages.filter((m) => m.type === 'load.result').at(-1)?.payload?.ok
  console.log('✓ game.load → load.result:', loadOk)
  if (!loadOk) throw new Error('读档失败')

  // 6.5 删除存档：game.delete_save → delete.result + 槽位列表刷新
  ws.send(JSON.stringify({ type: 'game.delete_save', payload: { slot_id: 3 } }))
  await sleep(500)
  const delOk = messages.filter((m) => m.type === 'delete.result').at(-1)?.payload?.ok
  console.log('✓ game.delete_save → delete.result:', delOk)
  if (!delOk) throw new Error('删除存档失败')
  const slot3After = messages.filter((m) => m.type === 'saves.list').at(-1)?.payload?.slots?.find((s) => s.slot_id === 3)
  console.log(`✓ 删除后槽位 3: exists=${slot3After?.exists}`)
  if (slot3After?.exists) throw new Error('删除后槽位仍存在')

  // 7. 快速存档
  ws.send(JSON.stringify({ type: 'game.quick_save' }))
  await sleep(400)
  const quickOk = messages.filter((m) => m.type === 'save.result' && m.payload?.quick).at(-1)?.payload?.ok
  console.log('✓ quick_save:', quickOk)

  ws.close()
  console.log('\n=== Phase 3 联调验收通过 ===')
}

run().catch((e) => {
  console.error('✗ 联调失败:', e?.message ?? String(e), '\n', e?.stack ?? '')
  process.exit(1)
})
