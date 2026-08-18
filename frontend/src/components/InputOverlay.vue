<script setup lang="ts">
import { ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'

const store = useGameStore()
const { input } = storeToRefs(store)
const value = ref('')

watch(input, (req) => {
  value.value = req?.default ?? ''
})

function submit(): void {
  store.submitInput(value.value)
}
</script>

<template>
  <div v-if="input" class="input-overlay">
    <div class="input-box">
      <p class="prompt">{{ input.prompt }}</p>
      <div class="row">
        <input
          v-model="value"
          class="field"
          type="text"
          :maxlength="input.maxLength"
          @keyup.enter="submit"
        />
        <button class="ok" @click="submit">确定</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.input-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(13, 15, 18, 0.85);
  backdrop-filter: blur(2px);
}

.input-box {
  width: min(480px, 80vw);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 24px 28px;
  animation: fadeUp 0.25s ease;
}

.prompt {
  font-family: var(--font-mono);
  font-size: 14px;
  color: var(--fg-dim);
  margin-bottom: 14px;
}

.row {
  display: flex;
  gap: 10px;
}

.field {
  flex: 1;
  padding: 10px 14px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--fg);
  font-family: var(--font-mono);
  font-size: 14px;
  outline: none;
}

.field:focus {
  border-color: var(--accent-dim);
}

.ok {
  padding: 10px 22px;
  background: var(--bg-elevated);
  border: 1px solid var(--accent-dim);
  border-radius: 6px;
  color: var(--accent);
  cursor: pointer;
  font-size: 14px;
}

.ok:hover {
  background: #1d232c;
}
</style>
