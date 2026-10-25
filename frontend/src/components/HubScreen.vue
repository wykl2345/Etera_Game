<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'
import StatusBar from './StatusBar.vue'

const store = useGameStore()
const { hubCharacters, hubCharButtons, hubSelectedChar, hubScene, toast } = storeToRefs(store)

/** 是否展开"移动"面板 */
const moveOpen = ref(false)

const selectedName = computed(
  () => hubCharacters.value.find((c) => c.char_id === hubSelectedChar.value)?.name ?? '',
)

/** 移动目标分组：同区域 / 跨区域 */
const sameRegion = computed(() => (hubScene.value?.adjacent ?? []).filter((s) => s.same_region))
const otherRegion = computed(() => (hubScene.value?.adjacent ?? []).filter((s) => !s.same_region))

/** 按钮上的消耗标注：⚡20 / 1/3 */
function costLabel(b: { stamina_cost: number; daily_limit: number; used_today: number | null }): string {
  const parts: string[] = []
  if (b.daily_limit > 0) parts.push(`${b.used_today ?? 0}/${b.daily_limit}`)
  if (b.stamina_cost > 0) parts.push(`⚡${b.stamina_cost}`)
  return parts.join(' ')
}
</script>

<template>
  <div class="hub">
    <StatusBar />

    <div class="hub-body">
      <!-- 当前场景 -->
      <header class="hub-head">
        <h2>
          {{ hubScene?.name ?? '未知地点' }}
          <span v-if="hubScene?.region_name" class="region">{{ hubScene.region_name }}</span>
        </h2>
        <p v-if="hubScene?.desc" class="hint">{{ hubScene.desc }}</p>
      </header>

      <!-- 本场景可交互的角色 -->
      <section class="chars">
        <button
          v-for="c in hubCharacters"
          :key="c.char_id"
          class="char-card"
          :class="{ selected: hubSelectedChar === c.char_id }"
          @click="store.selectHubChar(c.char_id)"
        >
          <span class="char-name">{{ c.name }}</span>
          <span class="char-rel">好感 {{ c.relation }}</span>
        </button>
        <p v-if="!hubCharacters.length" class="empty">（这里没有可以互动的人）</p>
      </section>

      <!-- 选中角色的行动 -->
      <section v-if="hubSelectedChar" class="actions">
        <div class="actions-title">{{ selectedName }} 的行动</div>
        <div class="actions-row">
          <button
            v-for="b in hubCharButtons"
            :key="b.event"
            class="action-btn"
            :disabled="!b.available"
            :title="b.available ? '' : (b.reason ?? '当前不可用')"
            @click="store.chooseHubButton(b)"
          >
            {{ b.label }}
            <span v-if="costLabel(b)" class="cost">{{ costLabel(b) }}</span>
            <span v-if="!b.available" class="lock">锁</span>
          </button>
          <!-- 引擎通用行动：送礼（不属于剧本按钮） -->
          <button class="action-btn" @click="store.openGift(hubSelectedChar!)">送礼</button>
          <p v-if="!hubCharButtons.length" class="empty">（该角色暂无可用行动）</p>
        </div>
      </section>

      <!-- 主角特殊功能栏 -->
      <section class="hero-bar">
        <span class="bar-label">主角</span>
        <button class="hero-btn" @click="moveOpen = !moveOpen">
          移动{{ moveOpen ? ' ▲' : ' ▼' }}
        </button>
        <button
          class="hero-btn"
          :disabled="!hubScene?.can_sleep"
          :title="hubScene?.can_sleep ? '睡一觉：恢复体力并进入下一天' : '这里睡不着（需要在有床的地方）'"
          @click="store.doSleep()"
        >睡觉</button>
        <button
          class="hero-btn"
          :disabled="hubScene?.id === 'home'"
          title="直接回自宅（无视相邻规则）"
          @click="store.goHome()"
        >回家</button>
        <button
          v-if="hubScene?.shop"
          class="hero-btn"
          :title="hubScene.shop.name"
          @click="store.openShop()"
        >购物</button>
        <button class="hero-btn" @click="store.openInventory()">背包</button>
        <button class="hero-btn" @click="store.openCharacters()">信息确认</button>
      </section>

      <!-- 移动面板：区域内 / 跨区域 分组 -->
      <section v-if="moveOpen" class="move-panel">
        <template v-if="sameRegion.length">
          <div class="actions-title">本区域内（{{ hubScene?.region_name }}）</div>
          <div class="actions-row">
            <button
              v-for="s in sameRegion"
              :key="s.id"
              class="action-btn"
              :title="s.desc"
              @click="store.moveTo(s.id)"
            >{{ s.name }}</button>
          </div>
        </template>
        <template v-if="otherRegion.length">
          <div class="actions-title" style="margin-top: 14px">前往其他区域</div>
          <div class="actions-row">
            <button
              v-for="s in otherRegion"
              :key="s.id"
              class="action-btn"
              :title="s.desc"
              @click="store.moveTo(s.id)"
            >
              {{ s.name }}
              <span class="cost">{{ s.region_name }}</span>
            </button>
          </div>
        </template>
        <p v-if="!sameRegion.length && !otherRegion.length" class="empty">（无处可去）</p>
      </section>

      <!-- 游戏功能按钮 -->
      <section class="system">
        <button class="sys-btn" @click="store.openSave()">保存</button>
        <button class="sys-btn" @click="store.openLoad()">读取</button>
        <button class="sys-btn" @click="store.openSettings()">设置</button>
        <button class="sys-btn" @click="store.runSelftest()">自检</button>
        <button class="sys-btn" @click="store.backToMenu()">主菜单</button>
      </section>
    </div>

    <Transition name="toast">
      <div v-if="toast" class="toast">{{ toast }}</div>
    </Transition>
  </div>
</template>

<style scoped>
.hub {
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: radial-gradient(ellipse at 50% 0%, #151b23, #0b0d10 70%);
  overflow: hidden;
}

.hub-body {
  flex: 1;
  overflow-y: auto;
  /* 顶部让出 52px：StatusBar 是 position:absolute，不占文档流 */
  padding: 68px 32px 40px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.hub-head h2 {
  margin: 0 0 6px;
  font-size: 20px;
  letter-spacing: 0.08em;
  color: var(--fg);
  font-weight: 500;
}
.hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--fg-dim);
  letter-spacing: 0.04em;
}
.region {
  margin-left: 10px;
  font-size: 11px;
  color: var(--fg-dim);
  letter-spacing: 0.08em;
  padding: 2px 8px;
  border-radius: 4px;
  background: #1d232c;
  font-weight: 400;
}

.chars {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.char-card {
  min-width: 132px;
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
  background: #14181e;
  border: 1px solid var(--border);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.16s ease;
  font-family: var(--font-mono);
}
.char-card:hover {
  border-color: var(--accent);
  background: #17202a;
  transform: translateY(-2px);
}
.char-card.selected {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, #14181e);
  box-shadow: 0 0 0 1px var(--accent) inset;
}
.char-name {
  font-size: 14px;
  color: var(--fg);
  letter-spacing: 0.06em;
}
.char-rel {
  font-size: 11px;
  color: var(--fg-dim);
}

.actions,
.move-panel {
  padding: 16px 18px;
  background: #101419;
  border: 1px solid var(--border);
  border-radius: 10px;
}
.actions-title {
  font-size: 12px;
  color: var(--fg-dim);
  letter-spacing: 0.1em;
  margin-bottom: 12px;
}
.actions-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.action-btn {
  padding: 9px 16px;
  font-size: 13px;
  letter-spacing: 0.06em;
  color: var(--fg);
  background: #1a2129;
  border: 1px solid var(--border);
  border-radius: 7px;
  cursor: pointer;
  font-family: var(--font-mono);
  transition: all 0.15s ease;
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.action-btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}
.action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.cost {
  font-size: 10px;
  color: var(--fg-dim);
  padding: 1px 5px;
  border-radius: 3px;
  background: #232a33;
}
.lock {
  font-size: 10px;
  color: var(--fg-dim);
}

.hero-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: #101419;
  border: 1px solid var(--border);
  border-radius: 10px;
}
.bar-label {
  font-size: 11px;
  letter-spacing: 0.14em;
  color: var(--fg-dim);
  padding: 2px 8px;
  border-radius: 4px;
  background: #1d232c;
}
.hero-btn {
  padding: 7px 16px;
  font-size: 12px;
  letter-spacing: 0.06em;
  color: var(--fg-dim);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  font-family: var(--font-mono);
  transition: all 0.15s ease;
}
.hero-btn:hover:not(:disabled) {
  color: var(--accent);
  border-color: var(--accent);
}
.hero-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.system {
  margin-top: auto;
  padding-top: 18px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.sys-btn {
  padding: 9px 18px;
  font-size: 13px;
  letter-spacing: 0.06em;
  color: var(--fg-dim);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 7px;
  cursor: pointer;
  font-family: var(--font-mono);
  transition: all 0.15s ease;
}
.sys-btn:hover {
  color: var(--accent);
  border-color: var(--accent);
}

.empty {
  margin: 0;
  font-size: 12px;
  color: var(--fg-dim);
  letter-spacing: 0.05em;
}

.toast {
  position: absolute;
  left: 50%;
  bottom: 28px;
  transform: translateX(-50%);
  padding: 8px 18px;
  background: rgba(22, 26, 32, 0.95);
  border: 1px solid var(--border);
  border-radius: 7px;
  font-size: 12px;
  color: var(--fg);
  z-index: 40;
}
.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.2s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
}
</style>
