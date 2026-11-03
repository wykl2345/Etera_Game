<script setup lang="ts">
/**
 * 小游戏模块（Overlay 注册表第一个模块）。
 * 只依赖 input（gameId）与 complete/cancel 事件，不直接读写 global store。
 */
import { computed } from 'vue'
import { findMinigame } from '../games'

const props = defineProps<{
  input: Record<string, unknown>
}>()

const emit = defineEmits<{
  complete: [result: Record<string, unknown>]
  cancel: []
}>()

const gameId = computed(() => String(props.input?.gameId ?? ''))
const def = computed(() => findMinigame(gameId.value))

function onFinish(result: Record<string, unknown>): void {
  emit('complete', result)
}
</script>

<template>
  <component v-if="def" :is="def.component" @finish="onFinish" @click.stop />
  <div v-else class="missing">
    <p>未找到小游戏：{{ gameId }}</p>
    <button class="btn" @click="emit('cancel')">返回</button>
  </div>
</template>

<style scoped>
.missing {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  background: var(--bg);
  color: var(--fg-dim);
  font-family: var(--font-mono);
}

.btn {
  padding: 9px 22px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--fg);
  cursor: pointer;
}
</style>
