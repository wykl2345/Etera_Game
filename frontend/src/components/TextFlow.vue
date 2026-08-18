<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'

const store = useGameStore()
const { textFlow } = storeToRefs(store)
const scrollBox = ref<HTMLElement | null>(null)

/** 新文本到达时自动滚动到底部 */
watch(
  () => textFlow.value.length,
  async () => {
    await nextTick()
    if (scrollBox.value) {
      scrollBox.value.scrollTop = scrollBox.value.scrollHeight
    }
  },
)
</script>

<template>
  <div ref="scrollBox" class="text-flow">
    <p
      v-for="(line, i) in textFlow"
      :key="i"
      class="line"
      :class="['tc-' + (line.color ?? 'white'), { bold: line.bold }]"
    >
      {{ line.text }}
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
  font-size: 15px;
  line-height: 1.9;
  padding-right: 8px;
}

.line {
  animation: fadeUp 0.25s ease;
}

.line.bold {
  font-weight: 700;
}

.placeholder {
  color: var(--fg-dim);
  opacity: 0.5;
}

.text-flow::-webkit-scrollbar {
  width: 6px;
}
.text-flow::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}
</style>
