<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'

const store = useGameStore()
const { connected } = storeToRefs(store)

function onStart(): void {
  store.startGame()
}

function quit(): void {
  // 浏览器环境无法真正关闭标签页，占位行为
  window.location.href = 'about:blank'
}
</script>

<template>
  <div class="main-menu">
    <div class="title-area">
      <h1 class="title">ETERA GAME</h1>
      <p class="subtitle">—— 幻想乡的日常冒险 ——</p>
    </div>

    <nav class="menu">
      <button class="menu-btn primary" @click="onStart">开始新游戏</button>
      <button class="menu-btn" disabled title="Phase 3 实现">继续游戏</button>
      <button class="menu-btn" disabled title="Phase 3 实现">设置</button>
      <button class="menu-btn" @click="quit">退出</button>
    </nav>

    <div class="conn-status" :class="{ online: connected }">
      {{ connected ? '● 已连接服务器' : '○ 未连接（后端未启动？）' }}
    </div>
  </div>
</template>

<style scoped>
.main-menu {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 48px;
  background:
    radial-gradient(ellipse at 50% 30%, rgba(232, 193, 90, 0.08), transparent 60%),
    var(--bg);
}

.title-area {
  text-align: center;
  animation: fadeUp 0.6s ease;
}

.title {
  font-family: var(--font-mono);
  font-size: clamp(40px, 8vw, 72px);
  letter-spacing: 0.35em;
  color: var(--fg);
  text-shadow: 0 0 24px rgba(232, 193, 90, 0.35);
  padding-left: 0.35em; /* 抵消 letter-spacing 造成的视觉偏移 */
}

.subtitle {
  margin-top: 12px;
  color: var(--fg-dim);
  font-size: 15px;
}

.menu {
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: min(320px, 70vw);
  animation: fadeUp 0.6s ease 0.15s both;
}

.menu-btn {
  padding: 13px 20px;
  font-size: 15px;
  letter-spacing: 0.2em;
  color: var(--fg);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.18s ease;
}

.menu-btn:hover:not(:disabled) {
  border-color: var(--accent-dim);
  background: #1d232c;
  transform: translateX(4px);
}

.menu-btn.primary {
  border-color: var(--accent-dim);
  color: var(--accent);
}

.menu-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.conn-status {
  position: absolute;
  bottom: 18px;
  font-size: 12px;
  color: var(--fg-dim);
  font-family: var(--font-mono);
}

.conn-status.online {
  color: var(--accent);
}
</style>
