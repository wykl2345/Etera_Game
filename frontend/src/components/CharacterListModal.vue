<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'
import type { CharSort } from '../stores/game'

const store = useGameStore()
const { sortedCharacters, charSort } = storeToRefs(store)

const SORTS: { key: CharSort; label: string }[] = [
  { key: 'relation', label: '好感' },
  { key: 'name', label: '姓名' },
  { key: 'location', label: '位置' },
]
</script>

<template>
  <div class="overlay" @click.self="store.closeCharacters()">
    <div class="panel">
      <header class="head">
        <h3>角色一览</h3>
        <div class="sorts">
          <span class="sort-label">排序</span>
          <button
            v-for="s in SORTS"
            :key="s.key"
            class="sort-btn"
            :class="{ active: charSort === s.key }"
            @click="store.setCharSort(s.key)"
          >{{ s.label }}</button>
        </div>
      </header>

      <ul class="list">
        <li
          v-for="c in sortedCharacters"
          :key="c.char_id"
          class="row"
          @click="store.openCharDetail(c.char_id)"
        >
          <div class="row-main">
            <span class="name">{{ c.name }}</span>
            <span class="title">{{ c.title }}</span>
            <span class="stage" :data-stage="c.relation_stage.key">
              {{ c.relation_stage.label }}
            </span>
            <span class="rel">好感 {{ c.relation }}</span>
          </div>
          <div class="row-sub">
            <span>HP {{ c.stats.hp }}/{{ c.stats.max_hp }}</span>
            <span>MP {{ c.stats.mp }}/{{ c.stats.max_mp }}</span>
            <span>体力 {{ c.stats.stamina }}/{{ c.stats.max_stamina }}</span>
            <span class="loc">{{ c.location || '—' }}</span>
            <span class="enter">查看 ›</span>
          </div>
        </li>
        <li v-if="!sortedCharacters.length" class="empty">（暂无角色）</li>
      </ul>

      <footer class="foot">
        <button class="btn" @click="store.closeCharacters()">返回</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: absolute;
  inset: 0;
  z-index: 35;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(10, 12, 15, 0.92);
  backdrop-filter: blur(3px);
}

.panel {
  width: min(680px, 92vw);
  max-height: 82vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px 24px;
  animation: fadeUp 0.22s ease;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}
.head h3 {
  margin: 0;
  font-size: 15px;
  letter-spacing: 0.1em;
  color: var(--fg);
  font-weight: 500;
}
.sorts {
  display: flex;
  align-items: center;
  gap: 6px;
}
.sort-label {
  font-size: 11px;
  color: var(--fg-dim);
  letter-spacing: 0.08em;
  margin-right: 2px;
}
.sort-btn {
  padding: 4px 10px;
  font-size: 11px;
  color: var(--fg-dim);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 5px;
  cursor: pointer;
  font-family: var(--font-mono);
  transition: all 0.15s ease;
}
.sort-btn:hover {
  color: var(--accent);
}
.sort-btn.active {
  color: var(--accent);
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}

.list {
  flex: 1;
  overflow-y: auto;
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.row {
  padding: 11px 14px;
  background: #14181e;
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.row:hover {
  border-color: var(--accent);
  background: #17202a;
}
.row-main {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 5px;
}
.name {
  font-size: 14px;
  color: var(--fg);
  letter-spacing: 0.05em;
}
.title {
  font-size: 11px;
  color: var(--fg-dim);
}
.stage {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 4px;
  background: #1d232c;
  color: var(--fg-dim);
}
.stage[data-stage='friendly'],
.stage[data-stage='close'] {
  color: #7fd88f;
}
.stage[data-stage='love'],
.stage[data-stage='soulmate'] {
  color: #e89ac8;
}
.stage[data-stage='distant'],
.stage[data-stage='hostile'] {
  color: #e07a6a;
}
.rel {
  margin-left: auto;
  font-size: 11px;
  color: var(--accent);
}
.row-sub {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: 11px;
  color: var(--fg-dim);
}
.loc {
  color: #7ab8e8;
}
.enter {
  margin-left: auto;
  color: var(--accent);
}

.empty {
  padding: 24px;
  text-align: center;
  font-size: 12px;
  color: var(--fg-dim);
}

.foot {
  padding-top: 14px;
  display: flex;
  justify-content: flex-end;
}
.btn {
  padding: 7px 20px;
  font-size: 12px;
  letter-spacing: 0.06em;
  color: var(--fg-dim);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  font-family: var(--font-mono);
}
.btn:hover {
  color: var(--accent);
  border-color: var(--accent);
}

@keyframes fadeUp {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
}
</style>
