<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'
import { useSettingsStore } from '../stores/settings'

const store = useGameStore()
const settings = useSettingsStore()
const { textSpeed, lineDelay, typewriterEnabled, fontSize, musicVolume } = storeToRefs(settings)
</script>

<template>
  <div class="settings-screen" @click.stop>
    <div class="panel">
      <h2 class="title">设置</h2>

      <div class="row">
        <span class="label">文字速度</span>
        <div class="control">
          <input
            type="range" min="8" max="40" step="1"
            :value="textSpeed"
            @input="settings.set('textSpeed', Number(($event.target as HTMLInputElement).value))"
          />
          <span class="hint">{{ textSpeed }} ms/字</span>
        </div>
      </div>

      <div class="row">
        <span class="label">行间停顿</span>
        <div class="control">
          <input
            type="range" min="0" max="2000" step="100"
            :value="lineDelay"
            @input="settings.set('lineDelay', Number(($event.target as HTMLInputElement).value))"
          />
          <span class="hint">{{ lineDelay }} ms</span>
        </div>
      </div>

      <div class="row">
        <span class="label">逐字打印</span>
        <div class="control">
          <button
            class="toggle"
            :class="{ on: typewriterEnabled }"
            @click="settings.set('typewriterEnabled', !typewriterEnabled)"
          >
            {{ typewriterEnabled ? '开' : '关' }}
          </button>
        </div>
      </div>

      <div class="row">
        <span class="label">正文字号</span>
        <div class="control">
          <div class="seg">
            <button
              v-for="size in (['small', 'medium', 'large'] as const)"
              :key="size"
              class="seg-btn"
              :class="{ active: fontSize === size }"
              @click="settings.set('fontSize', size)"
            >
              {{ { small: '小', medium: '中', large: '大' }[size] }}
            </button>
          </div>
        </div>
      </div>

      <div class="row">
        <span class="label">音乐音量</span>
        <div class="control">
          <input
            type="range" min="0" max="100" step="1"
            :value="Math.round(musicVolume * 100)"
            @input="settings.set('musicVolume', Number(($event.target as HTMLInputElement).value) / 100)"
          />
          <span class="hint">{{ Math.round(musicVolume * 100) }}%</span>
        </div>
      </div>

      <div class="footer">
        <button class="btn" @click="settings.reset">恢复默认</button>
        <button class="btn primary" @click="store.closeMenu">返回</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-screen {
  position: absolute;
  inset: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(10, 12, 15, 0.92);
  backdrop-filter: blur(3px);
}

.panel {
  width: min(480px, 90vw);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 26px 30px;
  animation: fadeUp 0.25s ease;
}

.title {
  font-family: var(--font-mono);
  font-size: 18px;
  letter-spacing: 0.2em;
  color: var(--accent);
  margin-bottom: 22px;
}

.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid var(--border);
}

.label {
  font-size: 14px;
  color: var(--fg);
}

.control {
  display: flex;
  align-items: center;
  gap: 10px;
}

input[type='range'] {
  width: 180px;
  accent-color: var(--accent-dim);
  cursor: pointer;
}

.hint {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--fg-dim);
  width: 62px;
}

.toggle {
  width: 56px;
  padding: 7px 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg-dim);
  font-size: 13px;
  cursor: pointer;
}

.toggle.on {
  border-color: var(--accent-dim);
  color: var(--accent);
}

.seg {
  display: flex;
  gap: 6px;
}

.seg-btn {
  width: 44px;
  padding: 7px 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg-dim);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.seg-btn.active {
  border-color: var(--accent-dim);
  color: var(--accent);
}

.footer {
  display: flex;
  gap: 10px;
  margin-top: 22px;
}

.btn {
  flex: 1;
  padding: 11px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--fg);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn:hover {
  border-color: var(--accent-dim);
  background: #1d232c;
}

.btn.primary {
  border-color: var(--accent-dim);
  color: var(--accent);
}
</style>
