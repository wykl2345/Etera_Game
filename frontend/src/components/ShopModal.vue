<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'

const store = useGameStore()
const { shopInfo, shopGoods } = storeToRefs(store)
</script>

<template>
  <div class="overlay" @click.self="store.closeMenu()">
    <div class="panel">
      <header class="head">
        <h3>{{ shopInfo?.name ?? '商店' }}</h3>
        <span class="money">所持金 {{ store.status?.player.money ?? 0 }}</span>
      </header>

      <ul class="goods">
        <li v-for="g in shopGoods" :key="g.id" class="good">
          <div class="info">
            <div class="line1">
              <span class="name">{{ g.name }}</span>
              <span class="price">{{ g.price }} 文</span>
            </div>
            <p class="desc">{{ g.desc }}</p>
            <p class="gift">送礼好感 +{{ g.gift_value }}</p>
          </div>
          <button
            class="buy"
            :disabled="!g.affordable"
            :title="g.affordable ? '' : '钱不够'"
            @click="store.buyItem(g.id)"
          >买入</button>
        </li>
        <li v-if="!shopGoods.length" class="empty">（这家店没有货）</li>
      </ul>

      <footer class="foot">
        <button class="btn" @click="store.closeMenu()">离开</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: absolute;
  inset: 0;
  z-index: 36;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(10, 12, 15, 0.92);
  backdrop-filter: blur(3px);
}
.panel {
  width: min(560px, 92vw);
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
  letter-spacing: 0.1em;
  color: var(--fg);
  font-weight: 500;
}
.money {
  font-size: 12px;
  color: var(--accent);
}

.goods {
  flex: 1;
  overflow-y: auto;
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.good {
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
.price {
  font-size: 12px;
  color: var(--accent);
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
.buy {
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
.buy:hover:not(:disabled) {
  color: var(--accent);
  border-color: var(--accent);
}
.buy:disabled {
  opacity: 0.35;
  cursor: not-allowed;
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
