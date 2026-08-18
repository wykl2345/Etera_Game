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
/** 每行已显示的字数 */
const revealed = ref<number[]>([])
const printing = ref(false)
let rafId = 0

// ── 自动滚动（新行到达 / 行开始打印时）──────────────
async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (scrollBox.value) {
    scrollBox.value.scrollTop = scrollBox.value.scrollHeight
  }
}

// ── 逐字打印驱动 ─────────────────────────────────
watch(
  textFlow,
  (flow) => {
    while (revealed.value.length < flow.length) revealed.value.push(0)
    scrollToBottom()
    if (!printing.value) startPrinting()
  },
  { immediate: true },
)

function startPrinting(): void {
  if (!typewriterEnabled.value) {
    revealed.value = textFlow.value.map((l) => l.text.length)
    return
  }
  printing.value = true
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
      if (!revealNext()) {
        cancelAnimationFrame(rafId)
        printing.value = false
        return
      }
    }
    rafId = requestAnimationFrame(tick)
  }
  rafId = requestAnimationFrame(tick)
}

function revealNext(): boolean {
  for (let i = 0; i < revealed.value.length; i++) {
    const line = textFlow.value[i]
    if (!line) continue
    if (revealed.value[i] < line.text.length) {
      const wasEmpty = revealed.value[i] === 0
      revealed.value[i]++
      if (wasEmpty) scrollToBottom() // 新行开始时滚动一次
      return true
    }
  }
  return false
}

/** 点击快进：当前行立即显示完整 */
function skip(): void {
  if (!printing.value) return
  for (let i = 0; i < revealed.value.length; i++) {
    const line = textFlow.value[i]
    if (revealed.value[i] < line.text.length) {
      revealed.value[i] = line.text.length
      return
    }
  }
}

function displayText(line: { text: string }, i: number): string {
  const count = revealed.value[i] ?? 0
  return line.text.slice(0, count)
}

watch(typewriterEnabled, () => {
  if (!typewriterEnabled.value) {
    revealed.value = textFlow.value.map((l) => l.text.length)
    cancelAnimationFrame(rafId)
    printing.value = false
  } else if (revealed.value.some((c, i) => c < (textFlow.value[i]?.text.length ?? 0))) {
    startPrinting()
  }
})

onUnmounted(() => cancelAnimationFrame(rafId))
</script>

<template>
  <div
    ref="scrollBox"
    class="text-flow"
    :class="fontSize"
    @click="skip"
  >
    <p
      v-for="(line, i) in textFlow"
      :key="i"
      class="line"
      :class="['tc-' + (line.color ?? 'white'), { bold: line.bold }]"
    >
      {{ displayText(line, i) }}<span v-if="printing && i === textFlow.length - 1" class="caret">▌</span>
    </p>
    <p v-if="!textFlow.length" class="placeholder">——</p>
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
}

.line.bold {
  font-weight: 700;
}

.caret {
  color: var(--accent);
  opacity: 0.7;
  animation: blink 0.8s step-end infinite;
}

@keyframes blink {
  50% { opacity: 0; }
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
