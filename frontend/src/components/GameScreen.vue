<script setup lang="ts">
import BackgroundLayer from './BackgroundLayer.vue'
import CharacterLayer from './CharacterLayer.vue'
import TextFlow from './TextFlow.vue'
import ChoiceMenu from './ChoiceMenu.vue'
import InputOverlay from './InputOverlay.vue'
</script>

<template>
  <div class="game-screen">
    <BackgroundLayer />
    <CharacterLayer />
    <div class="text-area">
      <TextFlow />
      <ChoiceMenu />
      <InputOverlay />
    </div>
    <div class="hud-corner">
      <span>ESC 返回主菜单</span>
    </div>
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
  padding: 20px 28px 24px;
  background: linear-gradient(to top, rgba(13, 15, 18, 0.96) 60%, rgba(13, 15, 18, 0));
}

.hud-corner {
  position: absolute;
  top: 14px;
  right: 18px;
  font-size: 11px;
  color: var(--fg-dim);
  font-family: var(--font-mono);
  opacity: 0.6;
}
</style>
