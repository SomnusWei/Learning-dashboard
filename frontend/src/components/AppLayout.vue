<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { useRouter } from 'vue-router'
import { SearchAPI, type SearchItem } from '@/api/search'
import { http } from '@/api/http'

const auth = useAuthStore()
const theme = useThemeStore()
const router = useRouter()

// 检测是否在 Tauri 桌面端运行
const isTauri = ref(false)
function checkTauri() {
  isTauri.value = typeof (window as any).__TAURI_INTERNALS__ !== 'undefined' || typeof (window as any).__TAURI__ !== 'undefined'
}

// 桌面端启动时：如果 localStorage 配置了不同的 backend URL，redirect 过去
// 用户首次启动需在设置里配置自己的 NAS IP（默认不写死，避免暴露示例 IP）
function applyDesktopBackendUrl() {
  if (!isTauri.value) return
  const target = localStorage.getItem('ld_desktop_backend_url')
  if (!target) {
    // 没有配置，跳转到设置页让用户配置
    return
  }
  const current = window.location.origin
  if (target !== current) {
    // 静默 redirect 到配置的 URL（用户在 Settings 主动切换时会 confirm，这里启动时直接 redirect）
    window.location.href = target
  }
}

// 获取 OCR 用的 backendUrl（优先用 localStorage 配置，回退到 window.location.origin）
function getBackendUrl() {
  return localStorage.getItem('ld_desktop_backend_url') || window.location.origin
}

// 截图 OCR 弹窗
const ocrModal = ref(false)
const ocrLoading = ref(false)
const ocrText = ref('')
const ocrError = ref('')
const ocrSaving = ref(false)
// OCR 解析后的结构化字段（科目/题型/答案/subject_id）
const ocrParsed = ref<any>(null)
const ocrSubject = ref('')
const ocrQuestionType = ref('')
const ocrAnswer = ref('')
// Rust 端自动保存的错题 ID（如果有，前端保存时改用 PUT 更新避免重复）
const ocrSavedId = ref<number | null>(null)

// 轻量 toast 提示（自动模式专用，不弹窗）
const toast = ref<{ message: string; type: 'success' | 'error' | 'info' } | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null
function showToast(message: string, type: 'success' | 'error' | 'info' = 'success', duration = 2500) {
  toast.value = { message, type }
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toast.value = null
  }, duration)
}

function ocrPreviewEnabled() {
  return localStorage.getItem('ld_ocr_preview') === '1'
}

async function doCaptureOcr() {
  if (!isTauri.value) {
    alert('此功能仅在桌面端可用')
    return
  }

  // 预览模式：弹窗显示识别结果，可编辑后保存
  if (ocrPreviewEnabled()) {
    ocrLoading.value = true
    ocrError.value = ''
    ocrText.value = ''
    ocrParsed.value = null
    ocrSubject.value = ''
    ocrQuestionType.value = ''
    ocrAnswer.value = ''
    ocrModal.value = true
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      const token = localStorage.getItem('ld_access_token') || ''
      const backendUrl = getBackendUrl()
      const result: any = await invoke('capture_and_ocr', { backendUrl, token })
      if (result.success) {
        const parsed = result.parsed || {}
        ocrParsed.value = parsed
        ocrSubject.value = parsed.subject || ''
        ocrQuestionType.value = parsed.question_type || ''
        ocrAnswer.value = parsed.answer || ''
        ocrText.value = parsed.content || result.text || '(未识别到文字)'
      } else {
        ocrError.value = result.error || '识别失败'
      }
    } catch (e: any) {
      ocrError.value = e?.message || String(e)
    } finally {
      ocrLoading.value = false
    }
    return
  }

  // 自动模式：OCR 成功后弹窗显示编辑表单，由用户手动保存
  // 先显示 loading toast，不立即弹窗（找不到窗口时不弹窗）
  showToast('正在截图识题…', 'info', 8000)
  try {
    const { invoke } = await import('@tauri-apps/api/core')
    const token = localStorage.getItem('ld_access_token') || ''
    const backendUrl = getBackendUrl()
    const result: any = await invoke('capture_and_ocr', { backendUrl, token })
    if (!result.success) {
      // 截图/OCR 失败（如找不到蓝基因窗口），不弹窗，仅 toast 提示
      const errMsg = result.error || '识别失败'
      showToast(`截图识题失败：${errMsg}`, 'error', 5000)
      return
    }
    // 成功：弹窗显示编辑表单
    ocrLoading.value = true
    ocrError.value = ''
    ocrText.value = ''
    ocrParsed.value = null
    ocrSubject.value = ''
    ocrQuestionType.value = ''
    ocrAnswer.value = ''
    ocrSavedId.value = null
    ocrModal.value = true
    const parsed = result.parsed || {}
    ocrParsed.value = parsed
    ocrSubject.value = parsed.subject || ''
    ocrQuestionType.value = parsed.question_type || ''
    ocrAnswer.value = parsed.answer || ''
    ocrText.value = parsed.content || result.text || '(未识别到文字)'
    // 记录 Rust 端自动保存的 ID（如果有），前端保存时改用 PUT 更新避免重复
    if (result.saved && result.saved_id) {
      ocrSavedId.value = result.saved_id
    }
  } catch (e: any) {
    const errMsg = e?.message || String(e)
    showToast(`截图识题异常：${errMsg}`, 'error', 5000)
  } finally {
    ocrLoading.value = false
  }
}

async function saveOcrAsWrongQuestion() {
  if (!ocrText.value.trim()) return
  ocrSaving.value = true
  try {
    const payload: any = { content: ocrText.value.trim() }
    if (ocrParsed.value?.subject_id) payload.subject_id = ocrParsed.value.subject_id
    if (ocrQuestionType.value) payload.question_type = ocrQuestionType.value
    if (ocrAnswer.value) payload.answer = ocrAnswer.value
    // 如果 Rust 端已自动保存（有 saved_id），改用 PUT 更新避免重复保存
    if (ocrSavedId.value) {
      await http.put(`/wrong-questions/${ocrSavedId.value}`, payload)
    } else {
      await http.post('/wrong-questions', payload)
    }
    ocrModal.value = false
    ocrText.value = ''
    ocrParsed.value = null
    ocrSubject.value = ''
    ocrQuestionType.value = ''
    ocrAnswer.value = ''
    ocrSavedId.value = null
    showToast('已保存到错题本，刷新中…', 'success', 1500)
    // 硬刷新，让用户看到真实落库结果
    setTimeout(() => location.reload(), 800)
  } catch (e: any) {
    showToast(`保存失败：${e?.message || ''}`, 'error', 5000)
  } finally {
    ocrSaving.value = false
  }
}

function closeOcrModal() {
  ocrModal.value = false
  ocrText.value = ''
  ocrError.value = ''
  ocrParsed.value = null
  ocrSubject.value = ''
  ocrQuestionType.value = ''
  ocrAnswer.value = ''
  ocrSavedId.value = null
}

// 全局搜索
const showSearch = ref(false)
const searchQuery = ref('')
const searchResults = ref<Record<string, SearchItem[]>>({})
const searchLoading = ref(false)
let searchTimer: ReturnType<typeof setTimeout> | null = null

function openSearch() {
  showSearch.value = true
  setTimeout(() => {
    const el = document.getElementById('global-search-input') as HTMLInputElement | null
    el?.focus()
  }, 50)
}

function closeSearch() {
  showSearch.value = false
  searchQuery.value = ''
  searchResults.value = {}
}

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  const q = searchQuery.value.trim()
  if (!q) {
    searchResults.value = {}
    return
  }
  searchLoading.value = true
  searchTimer = setTimeout(async () => {
    try {
      const r = await SearchAPI.search(q)
      searchResults.value = r.results || {}
    } catch {
      searchResults.value = {}
    } finally {
      searchLoading.value = false
    }
  }, 250)
}

async function gotoItem(item: SearchItem) {
  closeSearch()
  // 方歌库：base_id=-1，跳转到方歌库 tab
  if (item.base_id === -1) {
    router.push({ name: 'study', query: { tab: 'songs', focus: item.id } })
  } else {
    router.push({ name: 'study', query: { base_id: item.base_id, focus: item.id } })
  }
}

function onKeydown(e: KeyboardEvent) {
  // Ctrl+F 或 Cmd+F 唤出搜索（capture phase 拦截，阻止 webview 原生搜索框）
  if ((e.ctrlKey || e.metaKey) && (e.key === 'f' || e.key === 'F')) {
    e.preventDefault()
    e.stopPropagation()
    if (showSearch.value) {
      closeSearch()
    } else {
      openSearch()
    }
  }
  // Esc 关闭搜索
  if (e.key === 'Escape' && showSearch.value) {
    closeSearch()
  }
}

// 保存 unlisten 函数，组件卸载时清理
let unlistenShortcut: (() => void) | null = null
// 防止重复触发（按住 Alt+Q 或多次注册 listen 时只执行一次）
let ocrInProgress = false

onMounted(() => {
  checkTauri()
  // 桌面端：启动时如配置了不同 backend URL，redirect 过去
  applyDesktopBackendUrl()
  window.addEventListener('keydown', onKeydown, true)  // capture phase，先于 webview 原生搜索
  // 监听 Tauri 全局快捷键事件
  if (isTauri.value) {
    import('@tauri-apps/api/event').then(({ listen }) => {
      if (unlistenShortcut) return  // 已注册过，避免重复
      listen('shortcut-alt-q', () => {
        if (ocrInProgress) return  // 上次还在执行，跳过
        ocrInProgress = true
        doCaptureOcr().finally(() => {
          ocrInProgress = false
        })
      }).then((un) => { unlistenShortcut = un })
    })
  }
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown, true)
  if (unlistenShortcut) {
    unlistenShortcut()
    unlistenShortcut = null
  }
})

const totalResults = Object.values(searchResults.value).reduce((s, a) => s + (a?.length || 0), 0)

function onLogout() {
  auth.logout()
  router.push('/login')
}

const navItems = [
  { name: 'home', label: '首页', icon: '🏠' },
  { name: 'wrong-questions', label: '错题本', icon: '📝' },
  { name: 'plans', label: '学习计划', icon: '📅' },
  { name: 'todos', label: '待办事项', icon: '✅' },
  { name: 'study', label: '学习中心', icon: '📚' },
  { name: 'settings', label: '设置', icon: '⚙️' }
]
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <div class="logo">学</div>
        <span>学习台</span>
      </div>
      <nav class="nav">
        <router-link
          v-for="item in navItems"
          :key="item.name"
          :to="{ name: item.name }"
          class="nav-item"
          active-class="active"
        >
          <span class="icon">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <button class="btn-text" @click="theme.toggle()">
          {{ theme.mode === 'light' ? '🌙 黑夜' : '☀️ 白天' }}
        </button>
        <div class="user-info">
          <span v-if="auth.user">{{ auth.user.username }}</span>
          <button class="btn-text danger" @click="onLogout">退出</button>
        </div>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <div class="page-title">
          <slot name="title">{{ $route.meta.title || '学习工作台' }}</slot>
        </div>
        <div class="topbar-actions">
          <button v-if="isTauri" class="ocr-btn" title="截图识题 (Alt+Q)" @click="doCaptureOcr">
            📸 截图识题 <span class="kbd">Alt+Q</span>
          </button>
          <slot name="actions" />
        </div>
      </header>
      <div class="content">
        <slot />
      </div>
    </main>

    <!-- 全局搜索浮层 -->
    <div v-if="showSearch" class="search-overlay" @click.self="closeSearch">
      <div class="search-modal">
        <div class="search-input-wrap">
          <span class="search-icon">🔍</span>
          <input
            id="global-search-input"
            v-model="searchQuery"
            type="text"
            placeholder="搜索错题 / 待办（Esc 关闭）"
            @input="onSearchInput"
          />
          <span v-if="searchLoading" class="search-hint">搜索中…</span>
        </div>
        <div class="search-results">
          <div v-if="totalResults === 0 && !searchLoading && searchQuery" class="search-empty">
            没有匹配结果
          </div>
          <div v-for="(items, lib) in searchResults" :key="lib" class="search-group">
            <div class="search-group-title">{{ lib }}</div>
            <div
              v-for="item in items"
              :key="item.id"
              class="search-item"
              @click="gotoItem(item)"
            >
              <div class="search-name">{{ item.name }}</div>
              <div class="search-meta">
                {{ item.fields?.功效 || item.fields?.主治 || item.fields?.定位 || item.fields?.功用 || '' }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 截图 OCR 弹窗（点击外侧不关闭，必须点保存或关闭按钮） -->
    <div v-if="ocrModal" class="ocr-overlay">
      <div class="ocr-modal">
        <div class="ocr-header">
          <h3>📸 截图识题</h3>
          <button class="ocr-close" @click="closeOcrModal">✕</button>
        </div>
        <div class="ocr-body">
          <div v-if="ocrLoading" class="ocr-loading">
            <div class="spinner"></div>
            <p>正在截图并识别题目...</p>
          </div>
          <div v-else-if="ocrError" class="ocr-error">
            <p>❌ {{ ocrError }}</p>
            <button class="btn-primary" @click="doCaptureOcr">重新截图</button>
          </div>
          <div v-else>
            <div class="ocr-meta-row">
              <div class="ocr-field">
                <label>科目</label>
                <input v-model="ocrSubject" type="text" placeholder="如：中医内科学" readonly />
              </div>
              <div class="ocr-field">
                <label>题型</label>
                <input v-model="ocrQuestionType" type="text" placeholder="如：选择题-A1型题" />
              </div>
              <div class="ocr-field ocr-field-answer">
                <label>答案</label>
                <input v-model="ocrAnswer" type="text" placeholder="如：A" maxlength="5" />
              </div>
            </div>
            <p class="ocr-label">题目内容（可编辑后保存）：</p>
            <textarea v-model="ocrText" class="ocr-textarea" rows="12"></textarea>
            <div class="ocr-actions">
              <button class="btn-primary" :disabled="ocrSaving" @click="saveOcrAsWrongQuestion">
                {{ ocrSaving ? '保存中...' : '保存到错题本' }}
              </button>
              <button class="btn-secondary" @click="doCaptureOcr">重新截图</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Toast 提示 -->
    <div v-if="toast" class="toast" :class="toast.type">
      <span class="toast-icon">{{ toast.type === 'error' ? '❌' : toast.type === 'info' ? '⏳' : '✓' }}</span>
      <span class="toast-msg">{{ toast.message }}</span>
    </div>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  min-height: 100vh;
}
.sidebar {
  width: 220px;
  background: var(--bg-card);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
  position: sticky;
  top: 0;
  height: 100vh;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px 20px;
  font-weight: 600;
}
.logo {
  width: 36px; height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--color-primary), var(--color-accent));
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px;
}
.nav { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  font-size: 14px;
}
.nav-item:hover {
  background: var(--bg-main);
  color: var(--text-primary);
  text-decoration: none;
}
.nav-item.active {
  background: var(--color-primary);
  color: #fff;
}
.nav-item .icon { font-size: 16px; }
.sidebar-footer {
  border-top: 1px solid var(--border-color);
  padding-top: 12px;
  display: flex; flex-direction: column; gap: 8px;
}
.btn-text {
  background: transparent;
  color: var(--text-secondary);
  padding: 6px 12px;
  text-align: left;
  font-size: 13px;
}
.btn-text:hover { color: var(--color-primary); }
.btn-text.danger:hover { color: var(--color-accent); }
.user-info {
  display: flex; justify-content: space-between; align-items: center;
  padding: 0 12px;
  font-size: 13px;
  color: var(--text-secondary);
}
.main { flex: 1; min-width: 0; }
.topbar {
  height: 56px;
  border-bottom: 1px solid var(--border-color);
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px;
  background: var(--bg-card);
}
.page-title { font-weight: 600; font-size: 15px; }
.content { padding: 20px 24px; }

@media (max-width: 768px) {
  .sidebar { width: 64px; }
  .brand span, .nav-item span:not(.icon), .sidebar-footer .btn-text, .user-info { display: none; }
  .nav-item { justify-content: center; }
}

/* 全局搜索浮层 */
.search-overlay {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 200;
  display: flex; align-items: flex-start; justify-content: center;
  padding-top: 15vh;
}
.search-modal {
  width: 90%;
  max-width: 560px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}
.search-input-wrap {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-color);
}
.search-input-wrap .search-icon { font-size: 18px; opacity: 0.6; }
.search-input-wrap input {
  flex: 1; border: none; background: transparent;
  font-size: 16px; padding: 4px 0;
}
.search-input-wrap input:focus { outline: none; }
.search-hint { font-size: 12px; color: var(--text-secondary); }
.search-results {
  max-height: 50vh;
  overflow-y: auto;
  padding: 8px 0;
}
.search-empty { padding: 24px; text-align: center; color: var(--text-secondary); font-size: 13px; }
.search-group { padding: 4px 0; }
.search-group-title {
  font-size: 12px; color: var(--text-secondary);
  padding: 8px 18px 4px; font-weight: 600;
}
.search-item {
  padding: 8px 18px; cursor: pointer;
}
.search-item:hover { background: var(--bg-main); }
.search-name { font-size: 14px; font-weight: 500; }
.search-meta {
  font-size: 12px; color: var(--text-secondary); margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* 截图 OCR 按钮 */
.ocr-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: linear-gradient(135deg, var(--color-primary), var(--color-accent));
  color: #fff;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s;
}
.ocr-btn:hover { opacity: 0.88; }
.ocr-btn .kbd {
  font-size: 11px;
  padding: 1px 6px;
  background: rgba(255,255,255,0.25);
  border-radius: 4px;
  font-family: monospace;
}

/* OCR 弹窗 */
.ocr-overlay {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 300;
  display: flex; align-items: center; justify-content: center;
}
.ocr-modal {
  width: 90%; max-width: 640px;
  background: var(--bg-card);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}
.ocr-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
}
.ocr-header h3 { margin: 0; font-size: 16px; }
.ocr-close {
  background: none; border: none; font-size: 18px;
  color: var(--text-secondary); cursor: pointer;
}
.ocr-body { padding: 20px; }
.ocr-loading {
  display: flex; flex-direction: column; align-items: center;
  gap: 12px; padding: 40px 0; color: var(--text-secondary);
}
.spinner {
  width: 36px; height: 36px;
  border: 3px solid var(--border-color);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.ocr-error { text-align: center; padding: 20px 0; }
.ocr-label { font-size: 13px; color: var(--text-secondary); margin-bottom: 8px; }
.ocr-meta-row {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.ocr-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 120px;
}
.ocr-field-answer { max-width: 100px; flex: 0 0 100px; }
.ocr-field label {
  font-size: 12px;
  color: var(--text-secondary);
}
.ocr-field input {
  padding: 8px 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 14px;
  background: var(--bg-card);
  color: var(--text-primary);
}
.ocr-field input:focus {
  outline: none;
  border-color: var(--color-primary);
}
.ocr-field input[readonly] {
  background: var(--bg-muted, #f5f5f5);
  color: var(--text-secondary);
}
.ocr-textarea {
  width: 100%;
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-main);
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.6;
  resize: vertical;
  box-sizing: border-box;
}
.ocr-textarea:focus { outline: none; border-color: var(--color-primary); }
.ocr-actions { display: flex; gap: 10px; margin-top: 16px; }
.btn-primary {
  padding: 10px 20px;
  background: var(--color-primary);
  color: #fff;
  border-radius: var(--radius-sm);
  font-size: 14px;
  cursor: pointer;
  border: none;
}
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary {
  padding: 10px 20px;
  background: var(--bg-main);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 14px;
  cursor: pointer;
}

/* Toast 提示 */
.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  padding: 12px 18px;
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-lg);
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  z-index: 400;
  max-width: 420px;
  animation: toast-in 0.2s ease-out;
}
.toast.success { border-left: 3px solid #10b981; }
.toast.error { border-left: 3px solid #ef4444; }
.toast.info { border-left: 3px solid var(--color-primary); }
.toast-icon { font-size: 16px; }
.toast-msg { flex: 1; line-height: 1.4; }
@keyframes toast-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
