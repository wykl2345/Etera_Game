<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useGameStore } from '../stores/game'
import { computed, ref, watch } from 'vue'
import { ASSET_BASE } from '../stores/game'
import StatusBar from './StatusBar.vue'
import BackgroundLayer from './BackgroundLayer.vue'
import CharacterLayer from './CharacterLayer.vue'
import TextFlow from './TextFlow.vue'
import ChoiceMenu from './ChoiceMenu.vue'
import InputOverlay from './InputOverlay.vue'

const store = useGameStore()
const { uiMode, toast, cgImage } = storeToRefs(store)

/** CG 素材路径（缺图时显示占位） */
const cgUrl = computed(() =>
  cgImage.value ? `${ASSET_BASE}/images/cg/${cgImage.value}.png` : '',
)
const cgFailed = ref(false)
watch(cgImage, () => { cgFailed.value = false })
</script>

<template>
  <!-- 点击委托：背景/文本区点击推进文本；交互组件用 .stop 防冒泡 -->
  <div class="game-screen" @click="store.advanceText()">
    <!-- 叙事层：只在叙事/小游戏模式渲染。
         系统界面（存档/读档/设置）是全屏面板，若后面还留着叙事层，半透明
         背景会透出空文本区的 —— 占位符，看起来像"奇怪的缓存页"。 -->
    <template v-if="uiMode === 'game'">
      <StatusBar />

      <BackgroundLayer />
      <CharacterLayer />

      <!-- 全屏 CG 特写（DSL ui.cg）：有素材才盖住背景与立绘。
           素材缺失时**不渲染黑色层**，保留背景、只在角落提示，
           否则玩家会看到画面突然变黑（误以为 bug）。 -->
      <div v-if="cgImage && !cgFailed" class="cg-layer">
        <img :src="cgUrl" class="cg-img" alt="" @error="cgFailed = true" />
      </div>
      <div v-else-if="cgImage" class="cg-missing" :title="`放入 resources/images/cg/${cgImage}.png 即显示`">
        CG「{{ cgImage }}」素材未准备
      </div>

      <div class="text-area">
        <!-- 选项与输入框作为「文本流插槽」渲染，跟着对话走，而不是固定在下方 -->
        <TextFlow>
          <template #inline>
            <ChoiceMenu />
          </template>
        </TextFlow>
        <!-- 输入框是覆盖层（absolute，居中弹出），放在文本流外 -->
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

    <!-- 系统面板与覆盖层模块（小游戏）由 App.vue 的宿主渲染，不在此处 -->

    <!-- 兜底：任何未知/非法模式都不要渲染成“只有主题色的空壳”，
         给出可见错误与返回路径（正常情况下不会出现）。 -->
    <div
      v-if="uiMode !== 'game'"
      class="ui-broken"
      @click.stop
    >
      <h2>界面状态异常</h2>
      <p>当前模式：<code>{{ uiMode }}</code></p>
      <p>已记录最近 200 条 UI 状态转移（控制台 <code>window.__eteraUiLog</code> 可导出）。</p>
      <div class="ui-broken-actions">
        <button class="btn" @click="store.enterHub()">回到行动界面</button>
        <button class="btn" @click="store.backToMenu()">回到主菜单</button>
      </div>
    </div>

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

.cg-layer {
  position: absolute;
  inset: 0;
  z-index: 5;          /* 盖住背景(0)与立绘，但在文本区之下 */
  display: flex;
  align-items: center;
  justify-content: center;
  background: #08090b;
  animation: cgFade 0.45s ease;
}
.cg-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
/* 素材缺失：角落小标记，不遮挡画面 */
.cg-missing {
  position: absolute;
  top: 64px;
  right: 16px;
  z-index: 6;
  padding: 5px 10px;
  background: rgba(22, 26, 32, 0.85);
  border: 1px dashed var(--border);
  border-radius: 6px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--fg-dim);
  letter-spacing: 0.05em;
  pointer-events: none;
}
@keyframes cgFade {
  from { opacity: 0; }
}

.text-area {
  position: absolute;
  left: 0;
  right: 0;
  /* 必须高于 .cg-layer(5)：CG 特写时对话文本仍要显示在最上层 */
  z-index: 12;
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

.ui-broken {
  position: absolute;
  inset: 0;
  z-index: 30;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 32px;
  text-align: center;
  background: var(--bg);
  color: var(--fg-dim);
  font-family: var(--font-mono);
}
.ui-broken h2 {
  margin: 0 0 6px;
  color: var(--fg);
  font-size: 20px;
  letter-spacing: 0.12em;
}
.ui-broken p {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
}
.ui-broken code {
  color: var(--accent);
}
.ui-broken-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}
.ui-broken .btn {
  padding: 9px 22px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--fg);
  font-family: var(--font-mono);
  cursor: pointer;
}
.ui-broken .btn:hover {
  border-color: var(--accent-dim);
  color: var(--accent);
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
