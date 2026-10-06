<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { useRouter } from 'vue-router'
import { http } from '@/api/http'

const router = useRouter()
const visible = ref(false)
const query = ref('')
const results = ref<Record<string, any[]>>({})
const loading = ref(false)
let debounce: number | null = null

function open() {
  visible.value = true
  setTimeout(() => {
    const el = document.querySelector('[data-global-search] input') as HTMLInputElement | null
    el?.focus()
  }, 50)
}
function close() {
  visible.value = false
  query.value = ''
  results.value = {}
}

async function doSearch(q: string) {
  if (!q.trim()) {
    results.value = {}
    return
  }
  loading.value = true
  try {
    const { data } = await http.get('/search', { params: { q } })
    results.value = data.results || {}
  } catch (e) {
    results.value = {}
  } finally {
    loading.value = false
  }
}

function onInput() {
  if (debounce) clearTimeout(debounce)
  debounce = window.setTimeout(() => doSearch(query.value), 250)
}

function goto(lib: string, item: any) {
  close()
  router.push({ name: 'study', query: { base_id: item.base_id, focus: item.id } })
}

function onKey(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
    e.preventDefault()
    open()
  }
  if (e.key === 'Escape' && visible.value) {
    close()
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKey)
  // 暴露到全局点击触发
  ;(window as any).__openGlobalSearch = open
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
})

const totalResults = computed(() =>
  Object.values(results.value).reduce((sum, arr) => sum + (arr?.length || 0), 0)
)
</script>

<template>
  <div data-global-search v-if="visible" class="gs-overlay" @click.self="close">
    <div class="gs-card">
      <div class="gs-input">
        <span class="gs-icon">🔍</span>
        <input
          v-model="query"
          type="text"
          placeholder="搜索方剂 / 中药 / 穴位"
          @input="onInput"
          @keydown.enter="() => {}"
        />
        <span class="gs-esc">ESC</span>
      </div>

      <div v-if="loading" class="gs-loading">搜索中...</div>

      <div v-else-if="totalResults === 0 && query" class="gs-empty">没有匹配结果</div>

      <div v-else class="gs-results">
        <div v-for="(items, lib) in results" :key="lib" class="gs-group">
          <div class="gs-group-title">{{ lib }}</div>
          <div
            v-for="item in items"
            :key="item.id"
            class="gs-item"
            @click="goto(lib, item)"
          >
            <div class="gs-name">{{ item.name }}</div>
            <div class="gs-meta">{{ item.fields?.功效 || item.fields?.主治 || item.fields?.定位 || '' }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gs-overlay {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex; align-items: flex-start; justify-content: center;
  padding-top: 12vh;
  z-index: 9999;
}
.gs-card {
  width: 100%; max-width: 640px;
  background: var(--bg-card);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  overflow: hidden;
}
.gs-input {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-color);
}
.gs-icon { font-size: 18px; opacity: 0.6; }
.gs-input input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 15px;
  padding: 4px 0;
}
.gs-input input:focus { outline: none; }
.gs-esc {
  font-size: 11px;
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
  padding: 2px 8px;
  border-radius: 4px;
}
.gs-loading, .gs-empty {
  padding: 24px; text-align: center; color: var(--text-secondary);
  font-size: 13px;
}
.gs-results {
  max-height: 50vh; overflow-y: auto;
  padding: 8px 0;
}
.gs-group { padding: 0 8px 8px; }
.gs-group-title {
  font-size: 12px;
  color: var(--text-secondary);
  padding: 8px 10px 4px;
  font-weight: 600;
}
.gs-item {
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.gs-item:hover { background: var(--bg-main); }
.gs-name { font-size: 14px; font-weight: 500; }
.gs-meta {
  font-size: 12px; color: var(--text-secondary);
  margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
</style>
