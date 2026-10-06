import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const KEY = 'ld_theme'

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<'light' | 'dark'>(
    (localStorage.getItem(KEY) as 'light' | 'dark') ||
      (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
  )

  function apply(m: 'light' | 'dark') {
    mode.value = m
    document.documentElement.classList.toggle('dark', m === 'dark')
    localStorage.setItem(KEY, m)
  }

  function toggle() {
    apply(mode.value === 'light' ? 'dark' : 'light')
  }

  watch(mode, (m) => {
    document.documentElement.classList.toggle('dark', m === 'dark')
  })

  // 初始化
  document.documentElement.classList.toggle('dark', mode.value === 'dark')

  return { mode, apply, toggle }
})
