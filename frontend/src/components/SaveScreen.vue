<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useGameStore, type SaveSlotInfo } from '../stores/game'

defineProps<{
  mode: 'save' | 'load'
}>()

const store = useGameStore()
const { saves } = storeToRefs(store)

// ── 拖拽滚动（替代默认的文本选择）────────────────
const slotsEl = ref<HTMLElement | null>(null)
const dragging = ref(false)
let dragStartY = 0
let dragStartScrollTop = 0
let movedByDrag = false

function onMouseDown(e: MouseEvent): void {
  const el = slotsEl.value
  if (!el) return
  // 仅左键
  if (e.button !== 0) return
  dragStartY = e.clientY
  dragStartScrollTop = el.scrollTop
  movedByDrag = false
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

function onMouseMove(e: MouseEvent): void {
  const el = slotsEl.value
  if (!el) return
  const dy = e.clientY - dragStartY
  if (!movedByDrag && Math.abs(dy) > 5) {
    movedByDrag = true
    dragging.value = true
  }
  if (movedByDrag) {
    el.scrollTop = dragStartScrollTop - dy
  }
}

function onMouseUp(): void {
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
  dragging.value = false
}

function onSlot(slot: SaveSlotInfo): void {
  // 拖拽过的鼠标抬起不触发点击
  if (movedByDrag) {
    movedByDrag = false
    return
  }
  if (store.uiMode === 'save') {
    store.saveToSlot(slot.slot_id)
  } else {
    if (!slot.exists) {
      store.showToast('该槽位没有存档')
      return
    }
    store.loadFromSlot(slot.slot_id)
  }
}

function formatTime(t: string | undefined): string {
  return t ? t.slice(5, 16) : ''
}
</script>

<template>
  <div class="save-screen">
    <div class="panel">
      <h2 class="title">{{ mode === 'save' ? '保存游戏' : '读取存档' }}</h2>

      <div
        ref="slotsEl"
        class="slots"
        :class="{ dragging }"
        @mousedown="onMouseDown"
      >
        <div
          v-for="slot in saves"
          :key="slot.slot_id"
          class="slot"
          :class="{ empty: !slot.exists, quick: slot.slot_id === 0 }"
          @click="onSlot(slot)"
        >
          <span class="slot-id">{{ slot.slot_id === 0 ? '快速' : String(slot.slot_id).padStart(2, '0') }}</span>
          <div class="slot-body">
            <template v-if="slot.exists && slot.metadata">
              <span class="slot-day">第 {{ slot.metadata.day }} 天 · {{ slot.metadata.location }}</span>
              <span class="slot-time">{{ formatTime(slot.metadata.save_time) }}</span>
              <span class="slot-desc">{{ slot.metadata.description || '—' }}</span>
            </template>
            <span v-else class="slot-empty">空槽位</span>
          </div>
        </div>
      </div>

      <div class="footer">
        <button class="btn" @click="store.closeMenu">返回</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.save-screen {
  position: absolute;
  inset: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(10, 12, 15, 0.92);
  backdrop-filter: blur(3px);
}

.panel {
  width: min(560px, 92vw);
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 24px 28px;
  animation: fadeUp 0.25s ease;
}

.title {
  font-family: var(--font-mono);
  font-size: 18px;
  letter-spacing: 0.2em;
  color: var(--accent);
  margin-bottom: 18px;
}

.slots {
  overflow-y: auto;
  overflow-x: hidden; /* 禁止横向滚动条 */
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
  user-select: none; /* 拖拽滚动而非选择文字 */
  cursor: grab;
}

.slots.dragging {
  cursor: grabbing;
}

/* 拖拽时禁止槽位 hover 位移，避免抖动 */
.slots.dragging .slot:hover {
  transform: none;
  border-color: var(--border);
}

/* 自定义滚动条：透明背景 + 中间细线（不出现白色/粗轨道） */
.slots::-webkit-scrollbar {
  width: 4px;
}
.slots::-webkit-scrollbar-track {
  background: transparent;
}
.slots::-webkit-scrollbar-thumb {
  background: rgba(139, 143, 152, 0.35);
  border-radius: 2px;
}
.slots::-webkit-scrollbar-thumb:hover {
  background: rgba(139, 143, 152, 0.6);
}
.slots {
  scrollbar-width: thin;
  scrollbar-color: rgba(139, 143, 152, 0.35) transparent;
}

.slot {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 16px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.slot:hover {
  border-color: var(--accent-dim);
  transform: translateX(3px);
}

.slot.quick {
  border-color: var(--accent-dim);
}

.slot-id {
  font-family: var(--font-mono);
  color: var(--accent);
  font-size: 13px;
  width: 44px;
  flex-shrink: 0;
}

.slot-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-family: var(--font-mono);
  font-size: 12px;
}

.slot-day {
  color: var(--fg);
}

.slot-time {
  color: var(--fg-dim);
  font-size: 11px;
}

.slot-desc {
  color: var(--fg-dim);
  opacity: 0.8;
}

.slot-empty {
  color: var(--fg-dim);
  opacity: 0.5;
}

.footer {
  display: flex;
  gap: 10px;
  margin-top: 18px;
}

.btn {
  flex: 1;
  padding: 11px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--fg);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn:hover {
  border-color: var(--accent-dim);
  background: #1d232c;
}
</style>
