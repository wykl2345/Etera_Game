import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { initAudioHandlers } from './audio'
import './style.css'

initAudioHandlers()

createApp(App).use(createPinia()).mount('#app')
