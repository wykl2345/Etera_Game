<script setup lang="ts">
import { nextTick, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'
import { useSettingsStore } from '../stores/settings'

const store = useGameStore()
const settings = useSettingsStore()
const { textFlow } = storeToRefs(store)
const { typewriterEnabled, textSpeed, fontSize } = storeToRefs(settings)

const scrollBox = ref<HTMLElement | null>(null)

/** 已确认显示的段落数（整段完整显示过） */
const confirmed = ref(0)
/** 当前逐字打印中的行 index（-1 = 无） */
const activeIdx = ref(-1)
/** 每行已显示的字数 */
const revealed = ref<number[]>([])
/** 是否显示"▼ 点击继续" */
const showContinue = ref(false)

let rafId = 0

async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (scrollBox.value) {
    scrollBox.value.scrollTop = scrollBox.value.scrollHeight
  }
}

// ── 段落推进：新行到达 / 清空 ───────────────────────
watch(
  textFlow,
  (flow) => {
    if (!flow.length) {
      // ui.clear：重置段落状态
      confirmed.value = 0
      activeIdx.value = -1
      revealed.value = []
      showContinue.value = false
      cancelAnimationFrame(rafId)
      store.textIdle = true
      return
    }
    while (revealed.value.length < flow.length) revealed.value.push(0)
    // 当前段已打印完且后续行已到 → 显示 ▼（等点击）
    if (activeIdx.value >= 0 && confirmed.value + 1 < flow.length) {
      const line = flow[activeIdx.value]
      if (revealed.value[activeIdx.value] >= (line?.text.length ?? 0)) {
        showContinue.value = true
      }
    }
    // 空闲则开始下一段
    if (activeIdx.value === -1 && confirmed.value < flow.length) {
      startNext()
    }
    scrollToBottom()
  },
  { immediate: true, deep: true },
)

// 文本区空闲状态：无打印中、无待确认段落 → 选项/输入框可显示
watch(
  [confirmed, activeIdx, showContinue, () => textFlow.value.length],
  () => {
    store.textIdle = activeIdx.value === -1 && !showContinue.value
  },
  { immediate: true },
)

/** 开始逐字打印第 confirmed 段 */
function startNext(): void {
  if (confirmed.value >= textFlow.value.length) {
    activeIdx.value = -1
    return
  }
  activeIdx.value = confirmed.value
  showContinue.value = false
  if (!typewriterEnabled.value) {
    revealed.value[activeIdx.value] = textFlow.value[activeIdx.value].text.length
    onRevealDone()
    return
  }
  printing()
}

function printing(): void {
  cancelAnimationFrame(rafId)
  let acc = 0
  let last = performance.now()
  const step = () => Math.max(1, textSpeed.value)

  const tick = (now: number): void => {
    const dt = now - last
    last = now
    acc += dt
    let guard = 0
    while (acc >= step() && guard < 200) {
      acc -= step()
      guard++
      const idx = activeIdx.value
      const line = textFlow.value[idx]
      if (idx < 0 || !line) {
        cancelAnimationFrame(rafId)
        return
      }
      revealed.value[idx]++
      if (revealed.value[idx] >= line.text.length) {
        cancelAnimationFrame(rafId)
        onRevealDone()
        return
      }
    }
    rafId = requestAnimationFrame(tick)
  }
  rafId = requestAnimationFrame(tick)
}

/** 当前段逐字打印完成 */
function onRevealDone(): void {
  // 当前段（activeIdx）已完整显示 → 计入 confirmed（否则 displayText 会隐藏它）
  if (activeIdx.value >= 0) {
    confirmed.value = Math.max(confirmed.value, activeIdx.value + 1)
    activeIdx.value = -1
  }
  scrollToBottom()
  if (confirmed.value < textFlow.value.length) {
    if (store.autoAdvance) {
      // 自动播放模式：直接推进下一段（选项选择/输入提交/小游戏结束后的对话）
      startNext()
    } else {
      showContinue.value = true // 有后续行 → 等点击
    }
  }
  // 全部显示完：textIdle=true → 选项/输入框可显示
}

/** 推进文本（由 GameScreen 点击委托调用） */
function onAdvance(): void {
  if (showContinue.value) {
    confirmed.value++
    activeIdx.value = -1
    showContinue.value = false
    if (confirmed.value < textFlow.value.length) {
      startNext()
    }
    return
  }
  const idx = activeIdx.value
  const line = textFlow.value[idx]
  if (idx >= 0 && line && revealed.value[idx] < line.text.length) {
    // 快进当前段
    revealed.value[idx] = line.text.length
    cancelAnimationFrame(rafId)
    onRevealDone()
  }
}

// GameScreen 点击委托 → 推进文本（背景/文本区均可点击）
watch(
  () => store.textAdvanceTick,
  () => {
    if (store.textAdvanceTick > 0) onAdvance()
  },
)

function displayText(line: { text: string }, i: number): string {
  if (i < activeIdx.value || (i === activeIdx.value && activeIdx.value >= 0)) {
    return line.text.slice(0, revealed.value[i] ?? line.text.length)
  }
  if (i < confirmed.value) {
    return line.text
  }
  return ''
}

watch(typewriterEnabled, () => {
  if (activeIdx.value >= 0) {
    revealed.value[activeIdx.value] = textFlow.value[activeIdx.value]?.text.length ?? 0
    cancelAnimationFrame(rafId)
    onRevealDone()
  }
})

onUnmounted(() => cancelAnimationFrame(rafId))
</script>

<template>
  <!-- 点击推进由 GameScreen 根容器委托（背景/文本区均可点击） -->
  <div ref="scrollBox" class="text-flow" :class="fontSize">
    <p
      v-for="(line, i) in textFlow"
      :key="i"
      class="line"
      :class="['tc-' + (line.color ?? 'white'), { bold: line.bold }]"
    >
      {{ displayText(line, i) }}
    </p>
    <p v-if="!textFlow.length" class="placeholder">——</p>
    <p v-if="showContinue" class="continue-hint">▼ 点击继续</p>
  </div>
</template>

<style scoped>
.text-flow {
  max-height: 100%;
  overflow-y: auto;
  scroll-behavior: smooth;
  font-family: var(--font-mono);
  line-height: 1.9;
  padding-right: 8px;
  cursor: pointer;
}

/* 字号档位 */
.text-flow.small { font-size: 14px; }
.text-flow.medium { font-size: 16px; }
.text-flow.large { font-size: 18px; }

.line {
  animation: fadeUp 0.25s ease;
  word-break: break-all;
  white-space: pre-line; /* 支持 ui.text 内 \n 多行 */
}

.line.bold {
  font-weight: 700;
}

.continue-hint {
  margin-top: 6px;
  color: var(--accent);
  opacity: 0.7;
  font-size: 12px;
  animation: blink 1.2s ease-in-out infinite;
  user-select: none;
}

@keyframes blink {
  50% { opacity: 0.3; }
}

.placeholder {
  color: var(--fg-dim);
  opacity: 0.5;
}

.text-flow::-webkit-scrollbar {
  width: 4px;
}
.text-flow::-webkit-scrollbar-track {
  background: transparent;
}
.text-flow::-webkit-scrollbar-thumb {
  background: rgba(139, 143, 152, 0.3);
  border-radius: 2px;
}
</style>
