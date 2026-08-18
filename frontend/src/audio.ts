/**
 * 音频播放 —— 处理引擎推送的 audio.* 消息（HTMLAudioElement）
 * 素材缺失（404）或浏览器自动播放限制时静默忽略，不影响游戏。
 */
import { wsClient } from './ws/client'
import { useSettingsStore } from './stores/settings'
import { ASSET_BASE } from './stores/game'

let bgm: HTMLAudioElement | null = null
const sfxPool: HTMLAudioElement[] = []

function stopBgm(): void {
  if (bgm) {
    bgm.pause()
    bgm = null
  }
}

export function initAudioHandlers(): void {
  wsClient.on('audio.music_play', (m) => {
    const p = (m.payload ?? {}) as { name?: string; volume?: number; loop?: boolean }
    if (!p.name) return
    stopBgm()
    const settings = useSettingsStore()
    const audio = new Audio(`${ASSET_BASE}/audio/music/${p.name}.mp3`)
    audio.loop = !!p.loop
    audio.volume = Math.max(0, Math.min(1, (p.volume ?? 0.8) * settings.musicVolume))
    audio.play().catch(() => { /* 404 或自动播放限制，静默 */ })
    bgm = audio
  })

  wsClient.on('audio.music_stop', () => {
    stopBgm()
  })

  wsClient.on('audio.sound_play', (m) => {
    const p = (m.payload ?? {}) as { name?: string; volume?: number }
    if (!p.name) return
    const settings = useSettingsStore()
    const audio = new Audio(`${ASSET_BASE}/audio/sfx/${p.name}.mp3`)
    audio.volume = Math.max(0, Math.min(1, (p.volume ?? 1) * settings.musicVolume))
    audio.play().catch(() => {})
    sfxPool.push(audio)
    while (sfxPool.length > 8) {
      sfxPool.shift()?.pause()
    }
  })

  wsClient.on('audio.sound_stop', () => {
    sfxPool.forEach((a) => a.pause())
    sfxPool.length = 0
  })
}
