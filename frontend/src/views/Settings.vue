<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { http } from '@/api/http'
import { getToken } from '@/api/http'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import AppLayout from '@/components/AppLayout.vue'

const auth = useAuthStore()
const theme = useThemeStore()

const apiToken = computed(() => getToken() || '')
const tokenCopied = ref(false)

async function copyToken() {
  if (!apiToken.value) return
  try {
    await navigator.clipboard.writeText(apiToken.value)
    tokenCopied.value = true
    setTimeout(() => (tokenCopied.value = false), 2000)
  } catch {
    // 回退方案
    const ta = document.createElement('textarea')
    ta.value = apiToken.value
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    tokenCopied.value = true
    setTimeout(() => (tokenCopied.value = false), 2000)
  }
}

const study = reactive({ new_per_day: 20, review_per_day: 100 })

// 截图后弹窗预览开关（默认 false：自动发送 OCR）
const ocrPreview = ref(localStorage.getItem('ld_ocr_preview') === '1')
function toggleOcrPreview() {
  ocrPreview.value = !ocrPreview.value
  localStorage.setItem('ld_ocr_preview', ocrPreview.value ? '1' : '0')
}

// 桌面端连接路径（仅 Tauri 端使用，用户首次启动需在设置里配置自己的 NAS IP）
const backendUrlOptions = [
  { label: '内网 IP（示例 192.168.1.100，请改成你的 NAS IP）', value: 'https://192.168.1.100:8443' },
  { label: '备用内网 IP（示例 192.168.1.200）', value: 'https://192.168.1.200:8443' },
  { label: '域名（示例 your-domain.com，请改成你的域名）', value: 'https://your-domain.com:8443' },
]
const backendUrl = ref(localStorage.getItem('ld_desktop_backend_url') || '')
function selectBackendUrl(url: string) {
  backendUrl.value = url
  localStorage.setItem('ld_desktop_backend_url', url)
}
function applyBackendUrl() {
  if (!isTauri.value) return
  const target = backendUrl.value
  const current = window.location.origin
  if (target !== current) {
    if (confirm(`将切换连接路径到：${target}\n应用会刷新加载，确认继续？`)) {
      window.location.href = target
    }
  } else {
    alert('当前已使用该连接路径')
  }
}

// 检测是否在 Tauri 桌面端
const isTauri = ref(typeof (window as any).__TAURI_INTERNALS__ !== 'undefined' || typeof (window as any).__TAURI__ !== 'undefined')

async function openLogDir() {
  try {
    const { invoke } = await import('@tauri-apps/api/core')
    const path = await invoke<string>('open_log_dir')
    alert(`日志目录已打开：\n${path}`)
  } catch (e: any) {
    alert(`打开失败：${e?.message || String(e)}`)
  }
}

onMounted(async () => {
  try {
    const { data } = await http.get('/settings')
    if (data?.study) {
      study.new_per_day = data.study.new_per_day ?? 20
      study.review_per_day = data.study.review_per_day ?? 100
    }
  } catch (e) {
    // 容错
  }
})

async function saveSettings() {
  const { data } = await http.get('/settings')
  const settings = { ...(data || {}), study: { ...study } }
  await http.put('/settings', { settings })
  alert('已保存')
}

const exporting = ref(false)
async function exportData() {
  if (exporting.value) return
  exporting.value = true
  try {
    const res = await http.get('/settings/export', { responseType: 'blob' })
    const blob = new Blob([res.data], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `learning-dashboard-backup-${new Date().toISOString().slice(0, 10)}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e) {
    alert('导出失败')
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <AppLayout>
    <div class="settings">
      <h2>设置</h2>

      <section class="card">
        <h3>主题</h3>
        <div class="row">
          <span>当前模式：{{ theme.mode === 'light' ? '白天' : '黑夜' }}</span>
          <button class="btn-primary" @click="theme.toggle()">切换</button>
        </div>
      </section>

      <section class="card">
        <h3>学习设置</h3>
        <div class="field">
          <label>每日新卡上限</label>
          <input v-model.number="study.new_per_day" type="number" placeholder="20" />
        </div>
        <div class="field">
          <label>每日复习上限</label>
          <input v-model.number="study.review_per_day" type="number" placeholder="100" />
        </div>
      </section>

      <section v-if="isTauri" class="card">
        <h3>桌面端连接路径</h3>
        <p class="hint">选择桌面端访问后端的路径。内网 IP 速度更快但仅限内网，域名可在任何网络下访问。</p>
        <div class="backend-url-list">
          <button
            v-for="opt in backendUrlOptions"
            :key="opt.value"
            class="backend-url-btn"
            :class="{ active: backendUrl === opt.value }"
            @click="selectBackendUrl(opt.value)"
          >
            <span class="dot"></span>
            <span>{{ opt.label }}</span>
            <code>{{ opt.value }}</code>
          </button>
        </div>
        <div class="row">
          <span class="hint">当前已选：{{ backendUrl }}</span>
          <button class="btn-primary" @click="applyBackendUrl">应用并刷新</button>
        </div>
      </section>

      <section class="card">
        <h3>截图识题（Alt+Q）</h3>
        <div class="row">
          <div>
            <div>截图后弹窗预览</div>
            <p class="hint">关闭时自动发送 OCR 并保存到错题本（默认）；开启时弹窗显示识别结果，可编辑后再保存。</p>
          </div>
          <label class="switch">
            <input type="checkbox" :checked="ocrPreview" @change="toggleOcrPreview" />
            <span class="slider"></span>
          </label>
        </div>
        <div v-if="isTauri" class="row">
          <span>调试日志（截图 OCR 失败时查看）</span>
          <button class="btn-primary" @click="openLogDir">📂 打开日志目录</button>
        </div>
      </section>

      <section class="card">
        <h3>账号</h3>
        <div class="row">
          <span>用户名：{{ auth.user?.username }}</span>
          <button class="btn-primary" @click="saveSettings">保存设置</button>
        </div>
      </section>

      <section class="card">
        <h3>API Token</h3>
        <p class="hint">用于浏览器扩展「学习台剪藏」等外部应用调用。Token 会随登录刷新，失效后重新登录获取。</p>
        <div class="token-row">
          <input :value="apiToken ? apiToken.slice(0, 20) + '...' : '未登录'" readonly />
          <button class="btn-primary" :disabled="!apiToken" @click="copyToken">
            {{ tokenCopied ? '已复制 ✓' : '复制 Token' }}
          </button>
        </div>
      </section>

      <section class="card">
        <h3>数据备份</h3>
        <p class="hint">导出全部学习数据（知识库、卡片、学习记录等）为 JSON 文件，可用于备份或迁移。</p>
        <button class="btn-primary" :disabled="exporting" @click="exportData">
          {{ exporting ? '导出中...' : '📦 导出数据' }}
        </button>
      </section>
    </div>
  </AppLayout>
</template>

<style scoped>
.settings { display: flex; flex-direction: column; gap: 16px; }
h2 { font-size: 20px; }
.card { padding: 18px 20px; }
.card h3 { font-size: 15px; margin-bottom: 12px; color: var(--text-secondary); }
.row { display: flex; justify-content: space-between; align-items: center; }
.field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.field label { font-size: 13px; color: var(--text-secondary); }
.hint { font-size: 13px; color: var(--text-secondary); margin-bottom: 12px; line-height: 1.5; }

.backend-url-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.backend-url-btn {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  border: 1px solid var(--border); border-radius: 8px; background: var(--bg);
  cursor: pointer; transition: all .15s; text-align: left;
}
.backend-url-btn:hover { border-color: var(--primary); }
.backend-url-btn.active { border-color: var(--primary); background: color-mix(in srgb, var(--primary) 8%, var(--bg)); }
.backend-url-btn .dot {
  width: 10px; height: 10px; border-radius: 50%; border: 2px solid var(--border); flex-shrink: 0;
}
.backend-url-btn.active .dot { background: var(--primary); border-color: var(--primary); }
.backend-url-btn code { margin-left: auto; font-size: 12px; color: var(--text-secondary); }
.token-row { display: flex; gap: 10px; align-items: center; }
.token-row input {
  flex: 1; padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-main);
  color: var(--text-secondary);
  font-family: monospace;
  font-size: 13px;
}
button:disabled { opacity: 0.6; cursor: not-allowed; }

/* 开关组件 */
.switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
  flex-shrink: 0;
  cursor: pointer;
}
.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}
.switch .slider {
  position: absolute;
  inset: 0;
  background: var(--border-color);
  border-radius: 24px;
  transition: background 0.2s;
}
.switch .slider::before {
  content: "";
  position: absolute;
  left: 3px;
  top: 3px;
  width: 18px;
  height: 18px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.2s;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}
.switch input:checked + .slider {
  background: var(--color-primary);
}
.switch input:checked + .slider::before {
  transform: translateX(20px);
}
</style>
