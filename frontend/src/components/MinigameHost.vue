<script setup lang="ts">
/**
 * 小游戏宿主：按 store.activeMinigame.gameId 动态挂载注册表中的组件。
 * 子组件通过 emit('finish', result) 回传结果（ADR-0005 架构）。
 */
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'
import { findMinigame } from '../games'

const store = useGameStore()
const { activeMinigame } = storeToRefs(store)

const def = computed(() =>
  activeMinigame.value ? findMinigame(activeMinigame.value.gameId) : undefined,
)

function onFinish(result: Record<string, unknown>): void {
  store.finishMinigame(result)
}
</script>

<template>
  <component v-if="def" :is="def.component" @finish="onFinish" />
  <div v-else class="missing">
    <p>未找到小游戏：{{ activeMinigame?.gameId }}</p>
    <button class="btn" @click="store.popMode()">返回</button>
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
