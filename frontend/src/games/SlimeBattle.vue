<script setup lang="ts">
/**
 * 小游戏原型：史莱姆回合制战斗（Canvas 独立渲染层，ADR-0005 验证）
 * - 纯 Canvas 2D + requestAnimationFrame，与 Vue 主框架解耦
 * - 三张手牌：攻击 / 防御 / 治疗
 */
import { onMounted, onUnmounted, ref } from 'vue'

const emit = defineEmits<{
  finish: [result: { won: boolean; score: number; cancelled?: boolean }]
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const showResult = ref<'won' | 'lost' | null>(null)

interface Card {
  id: string
  name: string
  desc: string
  color: string
}

const CARDS: Card[] = [
  { id: 'atk', name: '攻击', desc: '造成 8-12 伤害', color: '#e07a6a' },
  { id: 'def', name: '防御', desc: '获得 6 护盾', color: '#7ab8e8' },
  { id: 'heal', name: '治疗', desc: '恢复 5 生命', color: '#7fd88f' },
]

const state = {
  player: { hp: 30, maxHp: 30, shield: 0 },
  enemy: { hp: 24, maxHp: 24 },
  phase: 'player' as 'player' | 'enemy',
}

let ctx: CanvasRenderingContext2D | null = null
let raf = 0
let enemyTimer: ReturnType<typeof setTimeout> | null = null

function rand(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min
}

// ── 绘制 ────────────────────────────────────────
function draw(): void {
  const canvas = canvasRef.value
  if (!canvas || !ctx) return
  const w = canvas.width
  const h = canvas.height

  // 背景
  ctx.fillStyle = '#0d0f12'
  ctx.fillRect(0, 0, w, h)
  ctx.fillStyle = '#161a20'
  ctx.fillRect(0, h * 0.32, w, h * 0.68)

  // 敌人（上方）
  drawSlime(w / 2, h * 0.2, state.enemy.hp / state.enemy.maxHp, '#7fd88f')
  drawBar(w / 2 - 80, h * 0.36, 160, state.enemy.hp, state.enemy.maxHp, '#e07a6a', '史莱姆')

  // 玩家（下方）
  drawPlayer(w / 2, h * 0.62, state.player.shield)
  drawBar(w / 2 - 80, h * 0.55, 160, state.player.hp, state.player.maxHp, '#7fd88f', '你')

  // 手牌（底部）
  if (state.phase === 'player') {
    const cardW = 120
    const cardH = 150
    const gap = 20
    const total = CARDS.length * cardW + gap * (CARDS.length - 1)
    let x = (w - total) / 2
    const y = h - cardH - 24
    CARDS.forEach((card) => {
      drawCard(x, y, cardW, cardH, card)
      x += cardW + gap
    })
  } else {
    ctx.fillStyle = '#8b8f98'
    ctx.font = '16px monospace'
    ctx.textAlign = 'center'
    ctx.fillText('敌方回合…', w / 2, h - 60)
  }
}

function drawSlime(x: number, y: number, hpRatio: number, color: string): void {
  if (!ctx) return
  ctx.save()
  ctx.translate(x, y)
  // 缩放随血量
  const scale = 0.8 + 0.2 * hpRatio
  ctx.scale(scale, scale)
  ctx.fillStyle = color
  ctx.beginPath()
  ctx.ellipse(0, 0, 55, 40, 0, 0, Math.PI * 2)
  ctx.fill()
  ctx.fillStyle = '#0d0f12'
  ctx.beginPath()
  ctx.ellipse(-16, -8, 6, 8, 0, 0, Math.PI * 2)
  ctx.ellipse(16, -8, 6, 8, 0, 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()
}

function drawPlayer(x: number, y: number, shield: number): void {
  if (!ctx) return
  ctx.save()
  ctx.translate(x, y)
  ctx.fillStyle = '#7ab8e8'
  ctx.beginPath()
  ctx.arc(0, 0, 34, 0, Math.PI * 2)
  ctx.fill()
  // 简单笑脸
  ctx.fillStyle = '#0d0f12'
  ctx.fillRect(-12, -6, 24, 4)
  ctx.fillRect(-12, 8, 8, 4)
  ctx.fillRect(4, 8, 8, 4)
  ctx.restore()
  if (shield > 0 && ctx) {
    ctx.strokeStyle = '#7ab8e8'
    ctx.lineWidth = 3
    ctx.globalAlpha = 0.7
    ctx.beginPath()
    ctx.arc(x, y, 46, 0, Math.PI * 2)
    ctx.stroke()
    ctx.globalAlpha = 1
    ctx.fillStyle = '#7ab8e8'
    ctx.font = '13px monospace'
    ctx.textAlign = 'center'
    ctx.fillText(`护盾 ${shield}`, x, y + 62)
  }
}

function drawBar(x: number, y: number, width: number, hp: number, max: number, color: string, label: string): void {
  if (!ctx) return
  ctx.fillStyle = '#232830'
  ctx.fillRect(x, y, width, 12)
  ctx.fillStyle = color
  ctx.fillRect(x, y, width * Math.max(0, hp / max), 12)
  ctx.fillStyle = '#d4d4d8'
  ctx.font = '13px monospace'
  ctx.textAlign = 'center'
  ctx.fillText(`${label} ${hp}/${max}`, x + width / 2, y + 34)
}

function drawCard(x: number, y: number, w: number, h: number, card: Card): void {
  if (!ctx) return
  ctx.fillStyle = '#161a20'
  ctx.strokeStyle = card.color
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.roundRect(x, y, w, h, 8)
  ctx.fill()
  ctx.stroke()
  ctx.fillStyle = card.color
  ctx.font = 'bold 17px monospace'
  ctx.textAlign = 'center'
  ctx.fillText(card.name, x + w / 2, y + 34)
  ctx.fillStyle = '#8b8f98'
  ctx.font = '12px monospace'
  ctx.fillText(card.desc, x + w / 2, y + 66)
  ctx.fillStyle = '#5a5f68'
  ctx.font = '11px monospace'
  ctx.fillText('点击使用', x + w / 2, y + h - 16)
}

// ── 交互 ────────────────────────────────────────
function onCanvasClick(e: MouseEvent): void {
  const canvas = canvasRef.value
  if (!canvas || state.phase !== 'player' || showResult.value) return
  const rect = canvas.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  const w = canvas.width
  const h = canvas.height
  const cardW = 120
  const cardH = 150
  const gap = 20
  const total = CARDS.length * cardW + gap * (CARDS.length - 1)
  const startX = (w - total) / 2
  const y0 = h - cardH - 24
  for (let i = 0; i < CARDS.length; i++) {
    const cx = startX + i * (cardW + gap)
    if (x >= cx && x <= cx + cardW && y >= y0 && y <= y0 + cardH) {
      playCard(i)
      return
    }
  }
}

function playCard(i: number): void {
  const card = CARDS[i]
  const s = state
  if (card.id === 'atk') s.enemy.hp = Math.max(0, s.enemy.hp - rand(8, 12))
  if (card.id === 'def') s.player.shield += 6
  if (card.id === 'heal') s.player.hp = Math.min(s.player.maxHp, s.player.hp + 5)
  checkEnd()
  if (showResult.value) return
  s.phase = 'enemy'
  enemyTimer = setTimeout(enemyTurn, 700)
}

function enemyTurn(): void {
  if (showResult.value) return
  const s = state
  let dmg = rand(5, 9)
  if (s.player.shield > 0) {
    const absorbed = Math.min(s.player.shield, dmg)
    s.player.shield -= absorbed
    dmg -= absorbed
  }
  s.player.hp = Math.max(0, s.player.hp - dmg)
  checkEnd()
  if (!showResult.value) s.phase = 'player'
}

function checkEnd(): void {
  if (state.enemy.hp <= 0) showResult.value = 'won'
  else if (state.player.hp <= 0) showResult.value = 'lost'
}

function reset(): void {
  state.player.hp = 30
  state.player.maxHp = 30
  state.player.shield = 0
  state.enemy.hp = 24
  state.enemy.maxHp = 24
  state.phase = 'player'
  showResult.value = null
}

function exit(): void {
  // 中途退出：按未完成处理（cancelled）
  emit('finish', { won: false, score: 0, cancelled: true })
}

function finish(): void {
  const won = showResult.value === 'won'
  emit('finish', { won, score: won ? state.player.hp : 0 })
}

// ── 生命周期 ────────────────────────────────────
function resize(): void {
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.parentElement?.getBoundingClientRect()
  if (!rect) return
  const dpr = window.devicePixelRatio || 1
  canvas.width = rect.width * dpr
  canvas.height = rect.height * dpr
  canvas.style.width = `${rect.width}px`
  canvas.style.height = `${rect.height}px`
  ctx?.setTransform(dpr, 0, 0, dpr, 0, 0)
}

onMounted(() => {
  const canvas = canvasRef.value
  if (!canvas) return
  ctx = canvas.getContext('2d')
  resize()
  window.addEventListener('resize', resize)
  canvas.addEventListener('click', onCanvasClick)
  const loop = (): void => {
    draw()
    raf = requestAnimationFrame(loop)
  }
  raf = requestAnimationFrame(loop)
})

onUnmounted(() => {
  cancelAnimationFrame(raf)
  if (enemyTimer) clearTimeout(enemyTimer)
  window.removeEventListener('resize', resize)
  canvasRef.value?.removeEventListener('click', onCanvasClick)
})
</script>

<template>
  <div class="slime-battle">
    <canvas ref="canvasRef" class="canvas" />
    <div class="hud">
      <span>小游戏原型（Canvas 实验）</span>
      <button class="exit-btn" @click="exit">返回</button>
    </div>
    <Transition name="result">
      <div v-if="showResult" class="result" :class="showResult">
        <h2>{{ showResult === 'won' ? '胜利！' : '战斗失败…' }}</h2>
        <p>{{ showResult === 'won' ? '你击败了史莱姆！' : '史莱姆太强了，再试一次？' }}</p>
        <div class="btns">
          <button class="btn" @click="reset">再来一次</button>
          <button class="btn primary" @click="finish">返回</button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.slime-battle {
  position: absolute;
  inset: 0;
  z-index: 20;
  background: #0d0f12;
}

.canvas {
  display: block;
}

.hud {
  position: absolute;
  top: 10px;
  left: 0;
  right: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 18px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--fg-dim);
}

.exit-btn {
  padding: 5px 14px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 5px;
  color: var(--fg-dim);
  font-size: 12px;
  cursor: pointer;
}

.exit-btn:hover {
  color: var(--accent);
  border-color: var(--accent-dim);
}

.result {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  background: rgba(10, 12, 15, 0.85);
  backdrop-filter: blur(2px);
}

.result h2 {
  font-family: var(--font-mono);
  font-size: 34px;
  letter-spacing: 0.2em;
}

.result.won h2 { color: var(--accent); }
.result.lost h2 { color: var(--danger); }

.result p {
  color: var(--fg-dim);
  font-size: 14px;
}

.btns {
  display: flex;
  gap: 12px;
  margin-top: 10px;
}

.btn {
  padding: 10px 26px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--fg);
  font-size: 14px;
  cursor: pointer;
}

.btn:hover { border-color: var(--accent-dim); }

.btn.primary {
  border-color: var(--accent-dim);
  color: var(--accent);
}

.result-enter-active,
.result-leave-active {
  transition: opacity 0.3s ease;
}
.result-enter-from,
.result-leave-to {
  opacity: 0;
}
</style>
