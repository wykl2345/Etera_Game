<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'

const store = useGameStore()
const { status } = storeToRefs(store)

const timeLabel = computed(() => {
  const map: Record<string, string> = {
    morning: '清晨', afternoon: '午后', evening: '黄昏', night: '夜晚', dawn: '黎明',
  }
  return map[status.value?.time_of_day ?? 'morning'] ?? status.value?.time_of_day ?? '—'
})

function pct(cur: number | undefined, max: number | undefined): number {
  if (cur == null || !max) return 0
  return Math.max(0, Math.min(100, (cur / max) * 100))
}
</script>

<template>
  <div class="status-bar">
    <div class="info">
      <span class="day">第 {{ status?.day ?? 1 }} 天</span>
      <span class="sep">|</span>
      <span class="time">{{ timeLabel }}</span>
      <span class="sep">|</span>
      <span class="loc">{{ status?.location_name ?? status?.location ?? '—' }}</span>
    </div>

    <div class="bars">
      <div class="bar hp">
        <span class="bar-label">HP</span>
        <div class="bar-track">
          <div class="bar-fill" :style="{ width: pct(status?.player.hp, status?.player.max_hp) + '%' }" />
        </div>
        <span class="bar-num">{{ status?.player.hp ?? 0 }}/{{ status?.player.max_hp ?? 0 }}</span>
      </div>
      <div class="bar mp">
        <span class="bar-label">MP</span>
        <div class="bar-track">
          <div class="bar-fill" :style="{ width: pct(status?.player.mp, status?.player.max_mp) + '%' }" />
        </div>
        <span class="bar-num">{{ status?.player.mp ?? 0 }}/{{ status?.player.max_mp ?? 0 }}</span>
      </div>
      <div class="bar stamina">
        <span class="bar-label">体</span>
        <div class="bar-track">
          <div class="bar-fill" :style="{ width: pct(status?.player.stamina, status?.player.max_stamina) + '%' }" />
        </div>
        <span class="bar-num">{{ status?.player.stamina ?? 0 }}/{{ status?.player.max_stamina ?? 0 }}</span>
      </div>
      <div class="money">
        <span class="coin">❖</span>{{ status?.player.money ?? 0 }}
      </div>
      <div class="level">Lv.{{ status?.player.level ?? 1 }}</div>
    </div>
  </div>
</template>

<style scoped>
.status-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 10;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 22px;
  background: linear-gradient(to bottom, rgba(13, 15, 18, 0.95), rgba(13, 15, 18, 0.75));
  border-bottom: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 13px;
  animation: fadeIn 0.3s ease;
}

.info {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--fg);
}

.day {
  color: var(--accent);
  letter-spacing: 0.08em;
}

.sep {
  color: var(--fg-dim);
  opacity: 0.5;
}

.time,
.loc {
  color: var(--fg-dim);
}

.bars {
  display: flex;
  align-items: center;
  gap: 16px;
}

.bar {
  display: flex;
  align-items: center;
  gap: 6px;
}

.bar-label {
  font-size: 11px;
  color: var(--fg-dim);
  width: 20px;
}

.bar-track {
  width: 90px;
  height: 8px;
  background: #232830;
  border-radius: 4px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}

.hp .bar-fill { background: linear-gradient(90deg, #7a2f2f, #e07a6a); }
.mp .bar-fill { background: linear-gradient(90deg, #2f4a7a, #7ab8e8); }
.stamina .bar-fill { background: linear-gradient(90deg, #5a7a2f, #a8d87a); }

.bar-num {
  font-size: 11px;
  color: var(--fg-dim);
}

.money {
  color: var(--accent);
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.coin {
  opacity: 0.8;
}

.level {
  color: var(--fg-dim);
  font-size: 12px;
}
</style>
