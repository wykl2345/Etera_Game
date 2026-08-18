/**
 * 客户端设置（纯前端偏好，localStorage 持久化）
 */
import { defineStore } from 'pinia'

export interface Settings {
  /** 逐字打印速度（每字毫秒数） */
  textSpeed: number
  /** 是否启用逐字打印 */
  typewriterEnabled: boolean
  /** 正文字号 */
  fontSize: 'small' | 'medium' | 'large'
  /** 音乐音量 0-1 */
  musicVolume: number
}

const STORAGE_KEY = 'etera-settings'

export const DEFAULT_SETTINGS: Settings = {
  textSpeed: 18,
  typewriterEnabled: true,
  fontSize: 'medium',
  musicVolume: 0.8,
}

function load(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_SETTINGS }
    return { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as Partial<Settings>) }
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

export const useSettingsStore = defineStore('settings', {
  state: (): Settings => load(),

  actions: {
    set<K extends keyof Settings>(key: K, value: Settings[K]): void {
      this.$patch({ [key]: value } as Partial<Settings>)
      this.persist()
    },

    reset(): void {
      Object.assign(this, { ...DEFAULT_SETTINGS })
      this.persist()
    },

    persist(): void {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({
          textSpeed: this.textSpeed,
          typewriterEnabled: this.typewriterEnabled,
          fontSize: this.fontSize,
          musicVolume: this.musicVolume,
        }))
      } catch {
        // localStorage 不可用时静默
      }
    },
  },
})
