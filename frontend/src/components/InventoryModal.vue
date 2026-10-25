<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { onMounted } from 'vue'
import { useGameStore } from '../stores/game'
import type { InventoryItem } from '../stores/game'

const store = useGameStore()
const { filteredInventory, invCategory } = storeToRefs(store)

const CATS: { key: 'all' | 'item' | 'equip' | 'skill' | 'key'; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'item', label: '普通' },
  { key: 'equip', label: '装备' },
  { key: 'skill', label: '技能' },
  { key: 'key', label: '重要' },
]

const countOf = (cat: string): number => {
  if (cat === 'all') return store.inventory.length
  return store.inventory.filter((i: InventoryItem) => i.category === cat).length
}

onMounted(() => store.refreshInventory())
</script>

<template>
  <div class="overlay" @click.self="store.closeMenu()">
    <div class="panel">
      <header class="head">
        <h3>背包</h3>
        <span class="money">所持金 {{ store.status?.player.money ?? 0 }}</span>
      </header>

      <!-- 分类页签 -->
      <div class="tabs">
        <button
          v-for="c in CATS"
          :key="c.key"
          class="tab"
          :class="{ active: invCategory === c.key }"
          @click="store.setInvCategory(c.key)"
        >
          {{ c.label }}
          <span v-if="countOf(c.key)" class="badge">{{ countOf(c.key) }}</span>
        </button>
      </div>

      <ul class="items">
        <li v-for="it in filteredInventory" :key="it.id" class="item">
          <div class="info">
            <div class="line1">
              <span class="name">{{ it.name }}</span>
              <span class="cat">{{ it.category_label }}</span>
              <span class="cnt">×{{ it.count }}</span>
            </div>
            <p v-if="it.desc" class="desc">{{ it.desc }}</p>
            <p class="tags">
              <span v-if="it.usable" class="usable">可使用</span>
              <span v-if="it.gift_value" class="gift">送礼 +{{ it.gift_value }}</span>
            </p>
          </div>
          <button
            v-if="it.usable"
            class="act"
            @click="store.useItem(it.id)"
          >使用</button>
          <span v-else class="act-idle">不可使用</span>
        </li>
        <li v-if="!filteredInventory.length" class="empty">
          （这一栏是空的）
        </li>
      </ul>

      <footer class="foot">
        <button class="btn" @click="store.closeMenu()">关闭</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: absolute;
  inset: 0;
  z-index: 37;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(10, 12, 15, 0.92);
  backdrop-filter: blur(3px);
}
.panel {
  width: min(600px, 92vw);
  max-height: 82vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px 24px;
  font-family: var(--font-mono);
  animation: fadeUp 0.2s ease;
}
.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.head h3 {
  margin: 0;
  font-size: 15px;
  letter-spacing: 0.1em;
  color: var(--fg);
  font-weight: 500;
}
.money {
  font-size: 12px;
  color: var(--accent);
}

.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 0 0;
}
.tab {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  font-size: 12px;
  color: var(--fg-dim);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 5px;
  cursor: pointer;
  font-family: var(--font-mono);
}
.tab:hover {
  color: var(--accent);
}
.tab.active {
  color: var(--accent);
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}
.badge {
  font-size: 10px;
  padding: 0 4px;
  border-radius: 3px;
  background: #232a33;
  color: var(--fg-dim);
}

.items {
  flex: 1;
  overflow-y: auto;
  list-style: none;
  margin: 10px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  background: #14181e;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.info {
  flex: 1;
  min-width: 0;
}
.line1 {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.name {
  font-size: 13px;
  color: var(--fg);
}
.cat {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #1d232c;
  color: var(--fg-dim);
}
.cnt {
  margin-left: auto;
  font-size: 12px;
  color: var(--fg-dim);
}
.desc {
  margin: 5px 0 0;
  font-size: 11px;
  color: var(--fg-dim);
  line-height: 1.6;
}
.tags {
  margin: 4px 0 0;
  display: flex;
  gap: 10px;
  font-size: 10px;
}
.usable {
  color: #7fd88f;
}
.gift {
  color: #e89ac8;
}

.act {
  flex-shrink: 0;
  padding: 7px 16px;
  font-size: 12px;
  color: var(--fg);
  background: #1a2129;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  font-family: var(--font-mono);
  transition: all 0.15s ease;
}
.act:hover {
  color: var(--accent);
  border-color: var(--accent);
}
.act-idle {
  flex-shrink: 0;
  font-size: 10px;
  color: #3a434d;
}
.empty {
  padding: 20px;
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
