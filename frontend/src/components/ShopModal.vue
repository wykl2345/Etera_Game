<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { onMounted } from 'vue'
import { useGameStore } from '../stores/game'

const store = useGameStore()
const { shopInfo, shopGoods, shopTab, inventory } = storeToRefs(store)

onMounted(() => {
  // 打开时确保两边数据都有
  if (!shopGoods.value.length) store.openShop()
  store.refreshInventory()
})
</script>

<template>
  <div class="overlay" @click.self="store.closeMenu()">
    <div class="panel">
      <header class="head">
        <h3>{{ shopInfo?.name ?? '商店' }}</h3>
        <span class="money">所持金 {{ store.status?.player.money ?? 0 }}</span>
      </header>

      <!-- 页签：买入 / 卖出 -->
      <div class="tabs">
        <button
          class="tab"
          :class="{ active: shopTab === 'buy' }"
          @click="store.setShopTab('buy')"
        >[买入]</button>
        <button
          class="tab"
          :class="{ active: shopTab === 'sell' }"
          @click="store.setShopTab('sell')"
        >[卖出]</button>
      </div>

      <!-- 买入 -->
      <ul v-if="shopTab === 'buy'" class="goods">
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
            class="act buy"
            :disabled="!g.affordable"
            :title="g.affordable ? '' : '钱不够'"
            @click="store.buyItem(g.id)"
          >买入</button>
        </li>
        <li v-if="!shopGoods.length" class="empty">（这家店没有货）</li>
      </ul>

      <!-- 卖出 -->
      <ul v-else class="goods">
        <li v-for="it in inventory" :key="it.id" class="good">
          <div class="info">
            <div class="line1">
              <span class="name">{{ it.name }} <span class="cnt">×{{ it.count }}</span></span>
              <span class="price">{{ it.sell_price }} 文</span>
            </div>
            <p v-if="it.desc" class="desc">{{ it.desc }}</p>
            <p class="gift">回收价约为原价一半</p>
          </div>
          <button
            class="act sell"
            :disabled="it.sell_price <= 0"
            :title="it.sell_price <= 0 ? '这个卖不出去' : ''"
            @click="store.sellItem(it.id)"
          >卖出</button>
        </li>
        <li v-if="!inventory.length" class="empty">（背包是空的，没东西可卖）</li>
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
  width: min(580px, 92vw);
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
  gap: 6px;
  padding: 10px 0 0;
}
.tab {
  padding: 5px 14px;
  font-size: 12px;
  color: var(--fg-dim);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 5px;
  cursor: pointer;
  font-family: var(--font-mono);
  letter-spacing: 0.06em;
}
.tab:hover {
  color: var(--accent);
}
.tab.active {
  color: var(--accent);
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}

.goods {
  flex: 1;
  overflow-y: auto;
  list-style: none;
  margin: 10px 0 0;
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
.cnt {
  font-size: 11px;
  color: var(--fg-dim);
  margin-left: 4px;
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
.act:hover:not(:disabled) {
  color: var(--accent);
  border-color: var(--accent);
}
.act:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.act.sell {
  color: #e8c15a;
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
