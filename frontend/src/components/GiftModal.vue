<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'

const store = useGameStore()
const { giftChar, inventory } = storeToRefs(store)

const charName = computed(
  () => store.charactersList.find((c) => c.char_id === giftChar.value)?.name
    ?? store.hubCharacters.find((c) => c.char_id === giftChar.value)?.name
    ?? '对方',
)

onMounted(() => {
  if (!store.inventory.length) {
    // 首次打开时拉一次背包
    store.refreshInventory()
  }
})
</script>

<template>
  <div class="overlay" @click.self="store.closeMenu()">
    <div class="panel">
      <header class="head">
        <h3>送给 {{ charName }}</h3>
        <span class="sub">背包里的东西</span>
      </header>

      <ul class="items">
        <li v-for="it in inventory" :key="it.id" class="item">
          <div class="info">
            <div class="line1">
              <span class="name">{{ it.name }}</span>
              <span class="count">×{{ it.count }}</span>
            </div>
            <p v-if="it.desc" class="desc">{{ it.desc }}</p>
            <p class="gift">好感 +{{ it.gift_value }}</p>
          </div>
          <button class="give" @click="store.sendGift(it.id)">送出</button>
        </li>
        <li v-if="!inventory.length" class="empty">
          （背包是空的 —— 去人间之里的市集买点东西吧）
        </li>
      </ul>

      <footer class="foot">
        <button class="btn" @click="store.closeMenu()">取消</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: absolute;
  inset: 0;
  z-index: 38;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(10, 12, 15, 0.92);
  backdrop-filter: blur(3px);
}
.panel {
  width: min(520px, 92vw);
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
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}
.head h3 {
  margin: 0;
  font-size: 15px;
  letter-spacing: 0.08em;
  color: var(--fg);
  font-weight: 500;
}
.sub {
  font-size: 11px;
  color: var(--fg-dim);
}

.items {
  flex: 1;
  overflow-y: auto;
  list-style: none;
  margin: 12px 0 0;
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
  justify-content: space-between;
  gap: 10px;
}
.name {
  font-size: 13px;
  color: var(--fg);
}
.count {
  font-size: 12px;
  color: var(--fg-dim);
}
.desc {
  margin: 5px 0 0;
  font-size: 11px;
  color: var(--fg-dim);
  line-height: 1.6;
}
.gift {
  margin: 4px 0 0;
  font-size: 10px;
  color: #7fd88f;
}
.give {
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
.give:hover {
  color: var(--accent);
  border-color: var(--accent);
}
.empty {
  padding: 20px;
  text-align: center;
  font-size: 12px;
  color: var(--fg-dim);
  line-height: 1.7;
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
