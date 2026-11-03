<script setup lang="ts">
/**
 * 覆盖层宿主（P3）：按 store.overlay.moduleId 渲染独立 UI 模块。
 * 模块完成后把结果交回 store；宿主本身不改变 uiMode，主界面保持挂载。
 */
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'
import { findOverlay } from '../overlays'

const store = useGameStore()
const { overlay } = storeToRefs(store)

const def = computed(() =>
  overlay.value ? findOverlay(overlay.value.moduleId) : undefined,
)

function onComplete(result: Record<string, unknown>): void {
  // 带上当前实例 id：旧模块的迟到回调不能关闭新打开的覆盖层
  store.completeOverlay(result, 'completed', 'component', overlay.value?.id)
}

function onCancel(): void {
  store.cancelOverlay('component', 'module-cancel', overlay.value?.id)
}
</script>

<template>
  <div v-if="overlay" class="overlay-host" @click.stop>
    <component
      v-if="def"
      :is="def.component"
      :input="overlay.input"
      @complete="onComplete"
      @cancel="onCancel"
    />
    <div v-else class="missing">
      <p>未注册的 UI 模块：{{ overlay.moduleId }}</p>
      <button class="btn" @click="onCancel">返回</button>
    </div>
  </div>
</template>

<style scoped>
.overlay-host {
  position: fixed;
  inset: 0;
  z-index: 60; /* 盖住根界面与系统面板 */
  background: transparent;
}

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
