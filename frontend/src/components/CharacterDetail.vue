<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useGameStore } from '../stores/game'

const store = useGameStore()

/** 当前页（0-based） */
const page = ref(0)

/** 切换角色时回到第一页 */
watch(() => store.detailChar, () => { page.value = 0 })

const ch = computed(() => store.detailCharacter)

const PAGES = ['基本', '属性', '记录'] as const

/** 属性名 → 中文标签（未列出的直接显示原名） */
const STAT_LABELS: Record<string, string> = {
  hp: '生命', max_hp: '生命上限',
  mp: '法力', max_mp: '法力上限',
  stamina: '体力', max_stamina: '体力上限',
  money: '金钱', exp: '经验', level: '等级',
}

const bar = (cur: number, max: number): number =>
  max <= 0 ? 0 : Math.max(0, Math.min(1, cur / max))

const tone = (ratio: number): string =>
  ratio > 0.5 ? '#7fd88f' : ratio >= 0.2 ? '#e8c15a' : '#e07a6a'

const hpRatio = computed(() => (ch.value ? bar(ch.value.stats.hp, ch.value.stats.max_hp) : 0))
const mpRatio = computed(() => (ch.value ? bar(ch.value.stats.mp, ch.value.stats.max_mp) : 0))
const stRatio = computed(() => (ch.value ? bar(ch.value.stats.stamina, ch.value.stats.max_stamina) : 0))

/** 好感度 -100..100 映射到 0..1（负数也能画出来） */
const relRatio = computed(() => (ch.value ? bar(ch.value.relation + 100, 200) : 0))

const flagEntries = computed(() =>
  ch.value ? Object.entries(ch.value.flags ?? {}) : [],
)
const statEntries = computed(() =>
  ch.value ? Object.entries(ch.value.stats ?? {}) : [],
)
</script>

<template>
  <div class="overlay" @click.self="store.closeCharDetail()">
    <div v-if="ch" class="panel">
      <header class="head">
        <div class="who">
          <span class="name">{{ ch.name }}</span>
          <span v-if="ch.title" class="title">{{ ch.title }}</span>
        </div>
        <div class="pager">
          <button class="arrow" :disabled="page === 0" @click="page--">‹</button>
          <span class="page-label">{{ PAGES[page] }} {{ page + 1 }}/{{ PAGES.length }}</span>
          <button class="arrow" :disabled="page === PAGES.length - 1" @click="page++">›</button>
        </div>
      </header>

      <!-- 每一页内容都控制在面板高度内（面板整体 max-height + 内容滚动） -->
      <div class="body">
        <!-- 页 1：基本 -->
        <section v-if="page === 0" class="page">
          <div class="kv-row">
            <span class="k">关系</span>
            <span class="v">
              <span class="stage" :data-stage="ch.relation_stage.key">
                {{ ch.relation_stage.label }}
              </span>
              <span class="rel-num">好感 {{ ch.relation }}</span>
            </span>
          </div>
          <div class="meter">
            <div class="meter-fill" :style="{ width: relRatio * 100 + '%', background: '#e89ac8' }" />
          </div>

          <div class="kv-row">
            <span class="k">生命</span>
            <span class="v">{{ ch.stats.hp }} / {{ ch.stats.max_hp }}</span>
          </div>
          <div class="meter">
            <div class="meter-fill" :style="{ width: hpRatio * 100 + '%', background: tone(hpRatio) }" />
          </div>

          <div class="kv-row">
            <span class="k">法力</span>
            <span class="v">{{ ch.stats.mp }} / {{ ch.stats.max_mp }}</span>
          </div>
          <div class="meter">
            <div class="meter-fill" :style="{ width: mpRatio * 100 + '%', background: '#7ab8e8' }" />
          </div>

          <div class="kv-row">
            <span class="k">体力</span>
            <span class="v">{{ ch.stats.stamina }} / {{ ch.stats.max_stamina }}</span>
          </div>
          <div class="meter">
            <div class="meter-fill" :style="{ width: stRatio * 100 + '%', background: tone(stRatio) }" />
          </div>

          <div class="kv-row">
            <span class="k">当前位置</span>
            <span class="v loc">{{ ch.location || '—' }}</span>
          </div>
          <div class="kv-row">
            <span class="k">标签</span>
            <span class="v">
              <span v-for="t in ch.tags" :key="t" class="tag">{{ t }}</span>
              <span v-if="!ch.tags.length" class="dim">—</span>
            </span>
          </div>
        </section>

        <!-- 页 2：属性明细 -->
        <section v-else-if="page === 1" class="page">
          <div v-for="[key, val] in statEntries" :key="key" class="kv-row">
            <span class="k">{{ STAT_LABELS[key] ?? key }}</span>
            <span class="v">{{ val }}</span>
          </div>
        </section>

        <!-- 页 3：标记 -->
        <section v-else class="page">
          <p class="hint">角色的专属开关（Flag）。未设置为 none 表示从未触发过。</p>
          <div v-for="[key, val] in flagEntries" :key="key" class="kv-row">
            <span class="k">{{ key }}</span>
            <span class="v" :class="{ on: val === true, off: val === false }">
              {{ val === true ? '已开启' : val === false ? '未开启' : String(val) }}
            </span>
          </div>
          <p v-if="!flagEntries.length" class="dim">（该角色没有记录任何 Flag）</p>
        </section>
      </div>

      <footer class="foot">
        <button class="btn" @click="store.closeCharDetail()">返回列表</button>
        <button class="btn" @click="store.closeCharacters()">关闭</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: absolute;
  inset: 0;
  z-index: 40; /* 盖在角色一览之上 */
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(10, 12, 15, 0.94);
  backdrop-filter: blur(4px);
}

.panel {
  width: min(520px, 90vw);
  max-height: 82vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px 24px;
  animation: fadeUp 0.2s ease;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}
.who {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.name {
  font-size: 16px;
  color: var(--fg);
  letter-spacing: 0.08em;
}
.title {
  font-size: 11px;
  color: var(--fg-dim);
}
.pager {
  display: flex;
  align-items: center;
  gap: 8px;
}
.arrow {
  width: 24px;
  height: 24px;
  font-size: 14px;
  line-height: 1;
  color: var(--fg-dim);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 5px;
  cursor: pointer;
  font-family: var(--font-mono);
}
.arrow:hover:not(:disabled) {
  color: var(--accent);
  border-color: var(--accent);
}
.arrow:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
.page-label {
  font-size: 11px;
  color: var(--fg-dim);
  letter-spacing: 0.06em;
  min-width: 72px;
  text-align: center;
}

/* 内容区滚动：保证单页内容不会把面板顶出屏幕 */
.body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 2px 4px;
}
.page {
  display: flex;
  flex-direction: column;
  gap: 9px;
}

.kv-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
}
.k {
  color: var(--fg-dim);
  letter-spacing: 0.06em;
  flex-shrink: 0;
}
.v {
  color: var(--fg);
  font-family: var(--font-mono);
  text-align: right;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.loc {
  color: #7ab8e8;
}

.meter {
  height: 6px;
  background: #1a1f26;
  border-radius: 3px;
  overflow: hidden;
  margin: -3px 0 3px;
}
.meter-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
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
.rel-num {
  color: var(--accent);
  font-size: 12px;
}

.tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #1d232c;
  color: var(--fg-dim);
  font-family: var(--font-mono);
}
.dim {
  color: var(--fg-dim);
  font-size: 12px;
}
.hint {
  margin: 0 0 8px;
  font-size: 11px;
  color: var(--fg-dim);
  line-height: 1.6;
}
.on {
  color: #7fd88f;
}
.off {
  color: var(--fg-dim);
}

.foot {
  padding-top: 14px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
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
