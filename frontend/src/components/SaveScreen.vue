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
  if (store.panel === 'save') {
    // 已有存档 → 先确认，避免误覆盖
    if (slot.exists) {
      confirmOverwrite.value = slot
      return
    }
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

// ── 覆盖/删除确认弹窗 ───────────────────────────
const confirmOverwrite = ref<SaveSlotInfo | null>(null)

function doOverwrite(): void {
  if (confirmOverwrite.value) {
    store.saveToSlot(confirmOverwrite.value.slot_id)
  }
  confirmOverwrite.value = null
}

// ── 删除确认弹窗 ────────────────────────────────
const confirmDelete = ref<SaveSlotInfo | null>(null)

function onDelete(slot: SaveSlotInfo): void {
  // 阻止冒泡到槽位点击（不触发保存/读档）
  confirmDelete.value = slot
}

function doDelete(): void {
  if (confirmDelete.value) {
    store.deleteSave(confirmDelete.value.slot_id)
  }
  confirmDelete.value = null
}
</script>

<template>
  <div class="save-screen" @click.stop>
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
              <span class="slot-day">第 {{ slot.metadata.day }} 天 · {{ slot.metadata.location_name ?? slot.metadata.location }}</span>
              <span class="slot-time">{{ formatTime(slot.metadata.save_time) }}</span>
              <span class="slot-desc">{{ slot.metadata.description || '—' }}</span>
            </template>
            <span v-else class="slot-empty">空槽位</span>
          </div>
          <button
            v-if="slot.exists"
            class="del-btn"
            title="删除存档"
            @click.stop="onDelete(slot)"
          >
            <span class="del-x">✕</span>
          </button>
        </div>
      </div>

      <div class="footer">
        <button class="btn" @click="store.closeMenu">返回</button>
      </div>

      <!-- 覆盖确认弹窗 -->
      <Transition name="confirm">
        <div v-if="confirmOverwrite" class="confirm-overlay">
          <div class="confirm-box">
            <h3>覆盖存档</h3>
            <p>
              槽位
              <span class="hl">{{ confirmOverwrite.slot_id === 0 ? '快速存档' : confirmOverwrite.slot_id }}</span>
              已有存档，确定覆盖吗？
            </p>
            <p v-if="confirmOverwrite.metadata" class="meta">
              第 {{ confirmOverwrite.metadata.day }} 天 ·
              {{ confirmOverwrite.metadata.location_name ?? confirmOverwrite.metadata.location }} ·
              {{ formatTime(confirmOverwrite.metadata.save_time) }}
            </p>
            <div class="btns">
              <button class="btn danger" @click="doOverwrite">覆盖</button>
              <button class="btn" @click="confirmOverwrite = null">取消</button>
            </div>
          </div>
        </div>
      </Transition>

      <!-- 删除确认弹窗 -->
      <Transition name="confirm">
        <div v-if="confirmDelete" class="confirm-overlay">
          <div class="confirm-box">
            <h3>删除存档</h3>
            <p>
              确定要删除槽位
              <span class="hl">{{ confirmDelete.slot_id === 0 ? '快速存档' : confirmDelete.slot_id }}</span>
              的存档吗？
            </p>
            <p v-if="confirmDelete.metadata" class="meta">
              第 {{ confirmDelete.metadata.day }} 天 · {{ formatTime(confirmDelete.metadata.save_time) }}
            </p>
            <div class="btns">
              <button class="btn danger" @click="doDelete">删除</button>
              <button class="btn" @click="confirmDelete = null">取消</button>
            </div>
          </div>
        </div>
      </Transition>
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

/* 删除按钮：圆角方形红叉 */
.del-btn {
  margin-left: auto;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 7px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.del-x {
  color: var(--fg-dim);
  font-size: 13px;
  line-height: 1;
}

.del-btn:hover {
  border-color: var(--danger);
  background: rgba(224, 122, 106, 0.1);
}

.del-btn:hover .del-x {
  color: var(--danger);
}

/* 删除确认弹窗 */
.confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(8, 10, 12, 0.75);
  backdrop-filter: blur(2px);
}

.confirm-box {
  width: min(360px, 84vw);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 24px 28px;
  animation: fadeUp 0.2s ease;
}

.confirm-box h3 {
  font-family: var(--font-mono);
  font-size: 16px;
  letter-spacing: 0.15em;
  color: var(--danger);
  margin-bottom: 12px;
}

.confirm-box p {
  font-size: 14px;
  color: var(--fg);
  line-height: 1.7;
}

.confirm-box .hl {
  color: var(--accent);
  font-family: var(--font-mono);
}

.confirm-box .meta {
  margin-top: 6px;
  font-size: 12px;
  color: var(--fg-dim);
  font-family: var(--font-mono);
}

.confirm-box .btns {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}

.confirm-box .btn.danger {
  border-color: var(--danger);
  color: var(--danger);
}

.confirm-box .btn.danger:hover {
  background: rgba(224, 122, 106, 0.12);
}

.confirm-enter-active,
.confirm-leave-active {
  transition: opacity 0.2s ease;
}
.confirm-enter-from,
.confirm-leave-to {
  opacity: 0;
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
