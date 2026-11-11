<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useGameStore, ASSET_BASE } from '../stores/game'

const store = useGameStore()
const { characters } = storeToRefs(store)

/** 对话默认靠右；left 留给双人/特殊站位 */
function posClass(position: string): string {
  return position === 'left' ? 'pos-left' : 'pos-right'
}

function imageUrl(charId: string, expression: string): string {
  // 规范目录结构：resources/images/characters/{id}/{expression}.png
  return `${ASSET_BASE}/images/characters/${charId}/${expression}.png`
}

/** 只有图片加载失败才显示占位卡片（不能和立绘同时出现） */
const failed = ref<Record<string, boolean>>({})

function keyOf(ch: { charId: string; expression: string }): string {
  return `${ch.charId}/${ch.expression}`
}

function onError(key: string): void {
  failed.value[key] = true
}
</script>

<template>
  <div class="char-layer">
    <div
      v-for="ch in characters.values()"
      :key="ch.charId"
      class="char-item"
      :class="posClass(ch.position)"
    >
      <img
        v-if="!failed[keyOf(ch)]"
        :src="imageUrl(ch.charId, ch.expression)"
        class="char-img"
        alt=""
        @error="onError(keyOf(ch))"
      />
      <!-- 无素材时才显示占位卡片 -->
      <div v-else class="char-fallback">
        <span class="char-id">{{ ch.charId }}</span>
        <span class="char-expr">{{ ch.expression }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.char-layer {
  position: absolute;
  inset: 0;
  /* 立绘在背景之上、文本框之下 */
  z-index: 1;
  pointer-events: none;
}

/*
 * 对话立绘：靠右、半身（容器裁掉大腿以下）。
 * 容器宽高比 0.95，而源图是 2:3；图片按宽度铺满后向下溢出，
 * overflow:hidden 只保留上半部，形成“半身像”。
 */
.char-item {
  position: absolute;
  bottom: 0;
  width: min(74.1vh, 60vw, 779px);
  aspect-ratio: 0.95;
  overflow: hidden;
  animation: fadeIn 0.6s ease;
}

.pos-right { right: 0; }
.pos-left { left: 0; }

.char-img {
  display: block;
  width: 100%;
  height: auto;
  filter: drop-shadow(0 0 20px rgba(0, 0, 0, 0.5));
}

/* 无素材占位：立绘名 + 表情 */
.char-fallback {
  position: absolute;
  inset: 0;
  border: 1px dashed var(--border);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: rgba(22, 26, 32, 0.7);
}

.char-id {
  font-family: var(--font-mono);
  color: var(--fg-dim);
  font-size: 14px;
  letter-spacing: 0.15em;
}

.char-expr {
  font-size: 11px;
  color: var(--fg-dim);
  opacity: 0.6;
}
</style>
