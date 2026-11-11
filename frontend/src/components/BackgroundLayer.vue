<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useGameStore, ASSET_BASE } from '../stores/game'

const store = useGameStore()
const { background } = storeToRefs(store)

/** 图片加载失败才显示渐变占位；不能再让占位层一直盖在图片上 */
const failed = ref(false)
watch(background, () => { failed.value = false })

/** 无真实图片资源：按背景名生成渐变占位（resources 补图后走真实 URL） */
const style = computed(() => {
  const name = background.value
  if (!name) {
    return { background: 'radial-gradient(ellipse at 50% 40%, #1a2029, #0d0f12 75%)' }
  }
  const hue = name.split('').reduce((a, c) => a + c.charCodeAt(0), 0) % 360
  return {
    background: `linear-gradient(160deg, hsl(${hue} 25% 18%), hsl(${(hue + 40) % 360} 30% 8%))`,
  }
})

const imageUrl = computed(() =>
  background.value ? `${ASSET_BASE}/images/backgrounds/${background.value}.png` : '',
)
const showImage = computed(() => !!background.value && !failed.value)
</script>

<template>
  <div class="bg-layer">
    <img
      v-if="showImage"
      :src="imageUrl"
      :key="background ?? ''"
      class="bg-img"
      alt=""
      @error="failed = true"
    />
    <div v-else class="bg-placeholder" :style="style">
      <span v-if="background" class="bg-name">{{ background }}</span>
    </div>
  </div>
</template>

<style scoped>
.bg-layer {
  position: absolute;
  inset: 0;
  z-index: 0;
}

.bg-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  animation: bgFade 0.45s ease;
}

@keyframes bgFade {
  from { opacity: 0; }
}

.bg-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.8s ease;
}

.bg-name {
  font-family: var(--font-mono);
  font-size: 13px;
  color: rgba(255, 255, 255, 0.12);
  letter-spacing: 0.3em;
}
</style>
