<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useGameStore, type SaveSlotInfo } from '../stores/game'

defineProps<{
  mode: 'save' | 'load'
}>()

const store = useGameStore()
const { saves } = storeToRefs(store)

function onSlot(slot: SaveSlotInfo): void {
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

      <div class="slots">
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
        <button class="btn" @click="store.quickSave">快速保存</button>
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
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
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
