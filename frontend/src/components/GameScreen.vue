<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'
import StatusBar from './StatusBar.vue'
import BackgroundLayer from './BackgroundLayer.vue'
import CharacterLayer from './CharacterLayer.vue'
import TextFlow from './TextFlow.vue'
import ChoiceMenu from './ChoiceMenu.vue'
import InputOverlay from './InputOverlay.vue'
import MinigameHost from './MinigameHost.vue'

const store = useGameStore()
const { uiMode, toast } = storeToRefs(store)
</script>

<template>
  <!-- 点击委托：背景/文本区点击推进文本；交互组件用 .stop 防冒泡 -->
  <div class="game-screen" @click="store.advanceText()">
    <!-- 叙事层：只在叙事/小游戏模式渲染。
         系统界面（存档/读档/设置）是全屏面板，若后面还留着叙事层，半透明
         背景会透出空文本区的 —— 占位符，看起来像"奇怪的缓存页"。 -->
    <template v-if="uiMode === 'game' || uiMode === 'minigame'">
      <StatusBar />

      <BackgroundLayer />
      <CharacterLayer />

      <div class="text-area">
        <TextFlow />
        <ChoiceMenu />
        <InputOverlay />
      </div>

    <!-- 底部工具条（系统界面，Web 化） -->
    <div v-if="uiMode === 'game'" class="toolbar" @click.stop>
      <!-- 存读档：对话/选项/小游戏进行中置灰（存档只含后端数据，中途存会存出半截画面） -->
      <button
        class="tool-btn" :disabled="!store.canPersist"
        :title="store.canPersist ? '存档到槽位' : '对话进行中，请先完成当前对话'"
        @click="store.openSave"
      >保存</button>
      <button
        class="tool-btn" :disabled="!store.canPersist"
        :title="store.canPersist ? '读取存档' : '对话进行中，请先完成当前对话'"
        @click="store.openLoad"
      >读取</button>
      <button
        class="tool-btn" :disabled="!store.canPersist"
        :title="store.canPersist ? '快速存档' : '对话进行中，请先完成当前对话'"
        @click="store.quickSave"
      >快存</button>
      <button
        class="tool-btn" :disabled="!store.canPersist"
        :title="store.canPersist ? '快速读取' : '对话进行中，请先完成当前对话'"
        @click="store.quickLoad"
      >快读</button>
      <button class="tool-btn" @click="store.openCharacters">角色</button>
      <button class="tool-btn" @click="store.openSettings">设置</button>
      <button
        class="tool-btn tool-btn--accent"
        :title="store.eventFinished ? '本段已结束，回到行动界面' : '提前结束本段并回到行动界面'"
        @click="store.enterHub()"
      >返回</button>
      <button class="tool-btn" @click="store.backToMenu">主菜单</button>
      </div>
    </template>

    <!-- save/load/settings 已上移到 App.vue 作为悬浮面板，不再在此渲染 -->
    <MinigameHost v-if="uiMode === 'minigame'" />

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

.tool-btn:hover:not(:disabled) {
  color: var(--accent);
  background: #1d232c;
}
.tool-btn--accent {
  color: var(--accent);
}
.tool-btn--accent:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 18%, transparent);
}
.tool-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
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
