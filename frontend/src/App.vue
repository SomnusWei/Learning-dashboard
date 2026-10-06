<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView, useRouter } from 'vue-router'
import { useThemeStore } from '@/stores/theme'
import GlobalSearch from '@/components/GlobalSearch.vue'

const theme = useThemeStore()
const router = useRouter()

onMounted(() => {
  // 全局 Ctrl+F 快捷搜索
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
      e.preventDefault()
      const el = document.querySelector('[data-global-search] input') as HTMLInputElement | null
      el?.focus()
    }
  })
})
</script>

<template>
  <RouterView v-slot="{ Component }">
    <transition name="fade" mode="out-in">
      <component :is="Component" />
    </transition>
  </RouterView>
  <GlobalSearch />
</template>

<style>
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
