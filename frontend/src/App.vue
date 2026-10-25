<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useGameStore } from './stores/game'
import MainMenu from './components/MainMenu.vue'
import HubScreen from './components/HubScreen.vue'
import GameScreen from './components/GameScreen.vue'

const store = useGameStore()
const { uiMode } = storeToRefs(store)

onMounted(() => {
  store.connect()
})
</script>

<template>
  <div class="app-root">
    <MainMenu v-if="uiMode === 'main_menu'" />
    <!-- Hub = 行动枢纽（系统界面）；game/minigame = 叙事界面 -->
    <HubScreen v-else-if="uiMode === 'hub'" />
    <GameScreen v-else />
  </div>
</template>

<style scoped>
.app-root {
  height: 100%;
}
</style>
