<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'
import StatusBar from './StatusBar.vue'
import BackgroundLayer from './BackgroundLayer.vue'
import CharacterLayer from './CharacterLayer.vue'
import TextFlow from './TextFlow.vue'
import ChoiceMenu from './ChoiceMenu.vue'
import InputOverlay from './InputOverlay.vue'
import SaveScreen from './SaveScreen.vue'

const store = useGameStore()
const { uiMode, toast } = storeToRefs(store)
</script>

<template>
  <div class="game-screen">
    <!-- 模式栈：状态栏仅 game 模式显示（ADR-0006 / v1 PRD 规则） -->
    <StatusBar v-if="uiMode === 'game'" />

    <BackgroundLayer />
    <CharacterLayer />

    <div class="text-area">
      <TextFlow />
      <ChoiceMenu />
      <InputOverlay />
    </div>

    <!-- 底部工具条（系统界面，Web 化） -->
    <div v-if="uiMode === 'game'" class="toolbar">
      <button class="tool-btn" @click="store.openSave">保存</button>
      <button class="tool-btn" @click="store.openLoad">读取</button>
      <button class="tool-btn" @click="store.quickSave" title="快速存档">快存</button>
      <button class="tool-btn" @click="store.quickLoad" title="快速读取">快读</button>
      <button class="tool-btn" @click="store.backToMenu">主菜单</button>
    </div>

    <SaveScreen v-if="uiMode === 'save'" mode="save" />
    <SaveScreen v-else-if="uiMode === 'load'" mode="load" />

    <Transition name="toast">
      <div v-if="toast" class="toast">{{ toast }}</div>
    </Transition>
  </div>
</template>

<style scoped>
.game-screen {
  position: relative;
  height: 100%;
  overflow: hidden;
}

.text-area {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  min-height: 220px;
  max-height: 46%;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  padding: 20px 28px 52px;
  background: linear-gradient(to top, rgba(13, 15, 18, 0.96) 60%, rgba(13, 15, 18, 0));
}

.toolbar {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 15;
  display: flex;
  gap: 8px;
  padding: 6px 10px;
  background: rgba(22, 26, 32, 0.9);
  border: 1px solid var(--border);
  border-radius: 8px;
  backdrop-filter: blur(2px);
}

.tool-btn {
  padding: 6px 14px;
  font-size: 12px;
  letter-spacing: 0.1em;
  color: var(--fg-dim);
  background: transparent;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-family: var(--font-mono);
  transition: all 0.15s ease;
}

.tool-btn:hover {
  color: var(--accent);
  background: #1d232c;
}

.toast {
  position: absolute;
  top: 64px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 40;
  padding: 10px 22px;
  background: var(--bg-elevated);
  border: 1px solid var(--accent-dim);
  border-radius: 6px;
  color: var(--accent);
  font-family: var(--font-mono);
  font-size: 13px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
}

.toast-enter-active,
.toast-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-6px);
}
</style>
