<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useGameStore } from './stores/game'
import MainMenu from './components/MainMenu.vue'
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
    <GameScreen v-else />
  </div>
</template>

<style scoped>
.app-root {
  height: 100%;
}
</style>
