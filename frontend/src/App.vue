<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useGameStore } from './stores/game'
import MainMenu from './components/MainMenu.vue'
import HubScreen from './components/HubScreen.vue'
import GameScreen from './components/GameScreen.vue'
import SaveScreen from './components/SaveScreen.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import CharacterListModal from './components/CharacterListModal.vue'
import CharacterDetail from './components/CharacterDetail.vue'
import ShopModal from './components/ShopModal.vue'
import GiftModal from './components/GiftModal.vue'
import InventoryModal from './components/InventoryModal.vue'

const store = useGameStore()
const { uiMode, panel, detailChar } = storeToRefs(store)

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

    <!-- 系统面板：悬浮在当前界面之上，不替换页面 -->
    <SaveScreen v-if="panel === 'save'" mode="save" />
    <SaveScreen v-else-if="panel === 'load'" mode="load" />
    <SettingsPanel v-if="panel === 'settings'" />
    <!-- 角色一览 → 点行进入详情（详情叠在列表之上） -->
    <CharacterListModal v-if="panel === 'characters'" />
    <CharacterDetail v-if="detailChar" />
    <ShopModal v-if="panel === 'shop'" />
    <GiftModal v-if="panel === 'gift'" />
    <InventoryModal v-if="panel === 'inventory'" />
  </div>
</template>

<style scoped>
.app-root {
  height: 100%;
  position: relative;   /* 悬浮面板的定位基准 */
}
</style>
