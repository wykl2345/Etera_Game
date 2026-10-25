<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useGameStore, ASSET_BASE } from '../stores/game'

const store = useGameStore()

/** 当前页（0-based） */
const page = ref(0)
/** 立绘加载失败（素材为空时显示占位） */
const portraitFailed = ref(false)

/** 切换角色时回到第一页、重置立绘状态 */
watch(() => store.detailChar, () => {
  page.value = 0
  portraitFailed.value = false
})

const ch = computed(() => store.detailCharacter)

const TABS = ['基本', '关系', '记录'] as const

/** 属性行（Emuera 风格的密集数值区） */
const STAT_ROWS: { key: string; label: string }[] = [
  { key: 'hp', label: '生命' },
  { key: 'mp', label: '法力' },
  { key: 'stamina', label: '体力' },
  { key: 'money', label: '金钱' },
  { key: 'exp', label: '经验' },
  { key: 'level', label: '等级' },
]

/** 关系阶段表（v1 设计文档 7 段，用于"当前阶段"高亮） */
const STAGES = [
  { label: '敌视', lo: -100, hi: -50 },
  { label: '疏远', lo: -49, hi: -10 },
  { label: '中立', lo: -9, hi: 9 },
  { label: '友人', lo: 10, hi: 29 },
  { label: '亲密', lo: 30, hi: 59 },
  { label: '恋爱', lo: 60, hi: 79 },
  { label: '伴侣', lo: 80, hi: 100 },
]

const portraitUrl = computed(() =>
  ch.value ? `${ASSET_BASE}/images/characters/${ch.value.char_id}/normal.png` : '',
)

/** 好感 -100..100 → 0..1 */
const relRatio = computed(() => {
  if (!ch.value) return 0
  return Math.max(0, Math.min(1, (ch.value.relation + 100) / 200))
})

/** 距下一阶段还差多少（已满级返回 null） */
const nextStage = computed(() => {
  if (!ch.value) return null
  const idx = STAGES.findIndex((s) => ch.value!.relation >= s.lo && ch.value!.relation <= s.hi)
  if (idx < 0 || idx >= STAGES.length - 1) return null
  const next = STAGES[idx + 1]
  return { label: next.label, gap: next.lo - ch.value.relation }
})

const flagEntries = computed(() => (ch.value ? Object.entries(ch.value.flags ?? {}) : []))

const statValue = (key: string): string => {
  if (!ch.value) return '—'
  const s = ch.value.stats
  const cur = s[key]
  const max = s[`max_${key}`]
  return max !== undefined ? `${cur} / ${max}` : String(cur ?? '—')
}
</script>

<template>
  <div class="overlay" @click.self="store.closeCharDetail()">
    <div v-if="ch" class="panel">
      <!-- 标题行（Emuera 风格 ■ ... ■） -->
      <header class="head">
        <div class="title-line">
          <span class="mark">■</span>
          <span class="name">{{ ch.name }}</span>
          <span v-if="ch.title" class="title">{{ ch.title }}</span>
          <span class="mark">■</span>
        </div>
        <div class="summary-line">
          <span class="kv">好感 <b>{{ ch.relation }}</b></span>
          <span class="sep">|</span>
          <span class="kv">阶段 <b class="stage" :data-stage="ch.relation_stage.key">{{ ch.relation_stage.label }}</b></span>
          <span class="sep">|</span>
          <span class="kv">HP <b>{{ ch.stats.hp }}/{{ ch.stats.max_hp }}</b></span>
          <span class="sep">|</span>
          <span class="kv">MP <b>{{ ch.stats.mp }}/{{ ch.stats.max_mp }}</b></span>
          <span class="sep">|</span>
          <span class="kv">体力 <b>{{ ch.stats.stamina }}/{{ ch.stats.max_stamina }}</b></span>
        </div>
      </header>

      <!-- 左信息 / 右立绘 -->
      <div class="content">
        <div class="info">
          <!-- ── 页 1：基本 ── -->
          <template v-if="page === 0">
            <div class="block-title">基本情报</div>
            <div class="rows">
              <div class="row"><span class="k">所在地点</span><span class="v">{{ ch.location || '—' }}</span></div>
              <div class="row">
                <span class="k">标签</span>
                <span class="v">
                  <span v-for="t in ch.tags" :key="t" class="tag">{{ t }}</span>
                  <span v-if="!ch.tags.length" class="dim">—</span>
                </span>
              </div>
            </div>

            <div class="block-title">属性</div>
            <div class="rows">
              <div v-for="s in STAT_ROWS" :key="s.key" class="row">
                <span class="k">{{ s.label }}</span>
                <span class="v mono">{{ statValue(s.key) }}</span>
              </div>
            </div>
          </template>

          <!-- ── 页 2：关系 ── -->
          <template v-else-if="page === 1">
            <div class="block-title">好感度</div>
            <div class="rel-head">
              <span class="stage big" :data-stage="ch.relation_stage.key">{{ ch.relation_stage.label }}</span>
              <span class="rel-val mono">{{ ch.relation }} / 100</span>
            </div>
            <div class="meter"><div class="meter-fill rel" :style="{ width: relRatio * 100 + '%' }" /></div>
            <p v-if="nextStage" class="hint">
              距「{{ nextStage.label }}」还差 <b>{{ nextStage.gap }}</b> 点好感
            </p>
            <p v-else class="hint">已达最高阶段「伴侣」</p>

            <div class="block-title">阶段对照</div>
            <div class="rows">
              <div
                v-for="s in STAGES"
                :key="s.label"
                class="row stage-row"
                :class="{ current: ch.relation >= s.lo && ch.relation <= s.hi }"
              >
                <span class="k">{{ s.label }}</span>
                <span class="v mono dim">{{ s.lo }} ~ {{ s.hi }}</span>
              </div>
            </div>
          </template>

          <!-- ── 页 3：记录 ── -->
          <template v-else>
            <div class="block-title">标记 (Flag)</div>
            <div class="rows">
              <div v-for="[key, val] in flagEntries" :key="key" class="row">
                <span class="k mono">{{ val === true ? '☑' : val === false ? '☐' : '·' }}</span>
                <span class="k">{{ key }}</span>
                <span class="v" :class="{ on: val === true }">
                  {{ val === true ? '已开启' : val === false ? '未开启' : String(val) }}
                </span>
              </div>
              <p v-if="!flagEntries.length" class="dim">（该角色没有记录任何 Flag）</p>
            </div>

            <div class="block-title">互动记录</div>
            <p class="hint">
              暂无记录。剧本可用 <code>data.set_flag("char:{{ ch.char_id }}", "键", 值)</code>
              写入角色专属标记；互动历史待后续版本实现。
            </p>
          </template>
        </div>

        <!-- 右侧立绘：素材放 resources/images/characters/{id}/normal.png 即显示 -->
        <aside class="portrait">
          <img
            v-if="!portraitFailed"
            :src="portraitUrl"
            class="portrait-img"
            alt=""
            @error="portraitFailed = true"
          />
          <div v-if="portraitFailed" class="portrait-ph">
            <span class="ph-name">{{ ch.name }}</span>
            <span class="ph-hint">立绘待补</span>
            <span class="ph-path mono">characters/{{ ch.char_id }}/normal.png</span>
          </div>
        </aside>
      </div>

      <!-- 底部页签（Emuera 风格 [1]page1 [2]page2） -->
      <footer class="foot">
        <div class="tabs">
          <button
            v-for="(t, i) in TABS"
            :key="t"
            class="tab"
            :class="{ active: page === i }"
            @click="page = i"
          >[{{ i + 1 }}] {{ t }}</button>
        </div>
        <div class="actions">
          <button class="btn" @click="store.closeCharDetail()">返回列表</button>
          <button class="btn" @click="store.closeCharacters()">关闭</button>
        </div>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: absolute;
  inset: 0;
  z-index: 40;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(10, 12, 15, 0.94);
  backdrop-filter: blur(4px);
}

.panel {
  width: min(880px, 94vw);
  max-height: 86vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 22px 14px;
  font-family: var(--font-mono);
  animation: fadeUp 0.2s ease;
}

/* ── 标题行 ── */
.head {
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.title-line {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 15px;
  letter-spacing: 0.06em;
}
.mark {
  color: var(--accent);
}
.name {
  color: var(--fg);
}
.title {
  font-size: 11px;
  color: var(--fg-dim);
}
.summary-line {
  margin-top: 7px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--fg-dim);
}
.summary-line b {
  color: var(--fg);
  font-weight: 400;
}
.sep {
  color: #2a3138;
}

/* ── 内容：左信息 / 右立绘 ── */
.content {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 18px;
  padding: 12px 0 8px;
}
.info {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding-right: 4px;
}

/* Emuera 风格区块标题：□ 名称 □──────── */
.block-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 14px 0 7px;
  font-size: 11px;
  color: var(--fg-dim);
  letter-spacing: 0.1em;
}
.block-title:first-child {
  margin-top: 0;
}
.block-title::before {
  content: '□';
  color: #3a434d;
}
.block-title::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}

.rows {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-size: 12px;
  line-height: 1.5;
}
.k {
  color: var(--fg-dim);
  flex-shrink: 0;
  min-width: 4.5em;
}
.v {
  color: var(--fg);
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.mono {
  font-family: var(--font-mono);
}
.dim {
  color: var(--fg-dim);
}

.tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #1d232c;
  color: var(--fg-dim);
}

/* 关系页 */
.rel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 6px;
}
.rel-val {
  font-size: 12px;
  color: var(--accent);
}
.meter {
  height: 7px;
  background: #1a1f26;
  border-radius: 3px;
  overflow: hidden;
}
.meter-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s ease;
}
.meter-fill.rel {
  background: linear-gradient(90deg, #7fd88f, #e89ac8);
}
.hint {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--fg-dim);
  line-height: 1.7;
}
.hint b {
  color: var(--accent);
  font-weight: 400;
}
.hint code {
  font-family: var(--font-mono);
  color: #7ab8e8;
  background: #151a20;
  padding: 0 4px;
  border-radius: 3px;
}
.stage-row.current .k,
.stage-row.current .v {
  color: var(--accent);
}
.stage-row.current::before {
  content: '▶';
  font-size: 9px;
  color: var(--accent);
  margin-right: -6px;
}

.stage {
  color: var(--fg-dim);
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 4px;
  background: #1d232c;
}
.stage.big {
  font-size: 12px;
  padding: 2px 10px;
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
.on {
  color: #7fd88f;
}

/* ── 右侧立绘 ── */
.portrait {
  width: 240px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0f1319;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
.portrait-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.portrait-ph {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 20px 12px;
  text-align: center;
}
.ph-name {
  font-size: 13px;
  color: var(--fg-dim);
  letter-spacing: 0.1em;
}
.ph-hint {
  font-size: 10px;
  color: #3a434d;
}
.ph-path {
  font-size: 9px;
  color: #2f373f;
  word-break: break-all;
  line-height: 1.5;
}

/* ── 底部 ── */
.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}
.tabs {
  display: flex;
  gap: 4px;
}
.tab {
  padding: 5px 10px;
  font-size: 11px;
  color: var(--fg-dim);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 5px;
  cursor: pointer;
  font-family: var(--font-mono);
  letter-spacing: 0.04em;
}
.tab:hover {
  color: var(--accent);
}
.tab.active {
  color: var(--accent);
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
}
.actions {
  display: flex;
  gap: 8px;
}
.btn {
  padding: 6px 16px;
  font-size: 11px;
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
