<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'

const store = useGameStore()
const { choice, textIdle } = storeToRefs(store)

function pick(index: number): void {
  store.choose(index)
}
</script>

<template>
  <!-- 选项只在文本区空闲时出现（对话看完才弹选项）；.stop 防止点击选项冒泡推进文本 -->
  <div v-if="choice && textIdle" class="choice-menu" @click.stop>
    <button
      v-for="(option, i) in choice.options"
      :key="i"
      class="choice-btn"
      @click="pick(i + 1)"
    >
      <span class="idx">{{ String(i + 1).padStart(2, '0') }}</span>
      <span class="label">{{ option }}</span>
    </button>
  </div>
</template>

<style scoped>
.choice-menu {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 16px;
  animation: fadeUp 0.3s ease;
}

.choice-btn {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 18px;
  text-align: left;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--fg);
  font-family: var(--font-mono);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.choice-btn:hover {
  border-color: var(--accent-dim);
  background: #1d232c;
  transform: translateX(4px);
}

.idx {
  color: var(--accent);
  opacity: 0.7;
  font-size: 12px;
}

.label {
  letter-spacing: 0.05em;
}
</style>
