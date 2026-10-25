<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'
import StatusBar from './StatusBar.vue'

const store = useGameStore()
const { hubCharacters, hubCharButtons, hubSelectedChar, toast } = storeToRefs(store)

const selectedName = computed(
  () => hubCharacters.value.find((c) => c.char_id === hubSelectedChar.value)?.name ?? '',
)
</script>

<template>
  <div class="hub">
    <StatusBar />

    <div class="hub-body">
      <header class="hub-head">
        <h2>今天要做什么？</h2>
        <p class="hint">选择一个角色，看看能和他/她做什么</p>
      </header>

      <!-- 角色卡片：点选后显示该角色注册的行动按钮 -->
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
        <p v-if="!hubCharacters.length" class="empty">（没有可互动的角色）</p>
      </section>

      <!-- 选中角色的行动按钮（由剧本 hub 声明注册，可带数值条件） -->
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
            <span v-if="!b.available" class="lock">锁</span>
          </button>
          <p v-if="!hubCharButtons.length" class="empty">（该角色暂无可用行动）</p>
        </div>
      </section>

      <!-- 游戏本身的功能按钮 -->
      <section class="system">
        <button class="sys-btn primary" @click="store.advanceDay()">下一天</button>
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
  padding: 28px 32px 40px;
  display: flex;
  flex-direction: column;
  gap: 26px;
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
  color: var(--fg-dim);
  letter-spacing: 0.05em;
}

/* ── 角色卡片 ── */
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

/* ── 角色行动 ── */
.actions {
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
  padding: 9px 18px;
  font-size: 13px;
  letter-spacing: 0.06em;
  color: var(--fg);
  background: #1a2129;
  border: 1px solid var(--border);
  border-radius: 7px;
  cursor: pointer;
  font-family: var(--font-mono);
  transition: all 0.15s ease;
}
.action-btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}
.action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.lock {
  margin-left: 6px;
  font-size: 10px;
  color: var(--fg-dim);
}

/* ── 游戏级按钮 ── */
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
.sys-btn.primary {
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
