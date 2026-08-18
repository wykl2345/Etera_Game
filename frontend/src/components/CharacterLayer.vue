<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useGameStore, ASSET_BASE } from '../stores/game'

const store = useGameStore()
const { characters } = storeToRefs(store)

function posClass(position: string): string {
  return `pos-${position}`
}

function imageUrl(charId: string, expression: string): string {
  // 规范目录结构：resources/images/characters/{id}/{expression}.png
  return `${ASSET_BASE}/images/characters/${charId}/${expression}.png`
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
        :src="imageUrl(ch.charId, ch.expression)"
        class="char-img"
        alt=""
        @error="(e) => ((e.target as HTMLImageElement).style.display = 'none')"
      />
      <!-- 无素材时显示占位卡片（img 加载失败自动隐藏） -->
      <div class="char-fallback">
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
  z-index: 1;
  pointer-events: none;
}

.char-item {
  position: absolute;
  bottom: 230px;
  width: 260px;
  height: 380px;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  animation: fadeIn 0.6s ease;
}

.pos-right { right: 12%; }
.pos-left { left: 12%; }
.pos-center { left: 50%; transform: translateX(-50%); }

.char-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  filter: drop-shadow(0 0 20px rgba(0, 0, 0, 0.5));
}

/* 无素材占位：立绘名 + 表情 */
.char-fallback {
  width: 100%;
  height: 100%;
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
