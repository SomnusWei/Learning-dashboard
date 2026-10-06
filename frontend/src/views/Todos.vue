<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { http } from '@/api/http'
import AppLayout from '@/components/AppLayout.vue'

interface Todo {
  id: number
  title: string
  description: string | null
  url: string | null
  source: string
  priority: number
  status: string
  due_date: string | null
  completed_at: string | null
  tags: string[]
  ref_type: string | null
  ref_id: number | null
  created_at: string
}

const todos = ref<Todo[]>([])
const filterStatus = ref<'all' | 'pending' | 'done'>('all')
const filterPriority = ref<number | null>(null)
const showForm = ref(false)
const editingId = ref<number | null>(null)
const msg = ref('')

// 方歌弹窗
const songModalOpen = ref(false)
const currentSong = ref<any>(null)
const songLoading = ref(false)

async function openFormulaSong(songId: number) {
  songModalOpen.value = true
  songLoading.value = true
  currentSong.value = null
  try {
    const r = await http.get(`/formula-songs/${songId}`)
    currentSong.value = r.data
  } catch (e: any) {
    alert(`加载方歌失败：${e?.response?.data?.detail || e?.message || ''}`)
    songModalOpen.value = false
  } finally {
    songLoading.value = false
  }
}
function closeSongModal() {
  songModalOpen.value = false
  currentSong.value = null
}
async function completeSongTodo(todo: any) {
  // 在弹窗里直接完成待办
  const t = todos.value.find((x) => x.ref_type === 'formula_song' && x.ref_id === currentSong.value?.id)
  if (t) {
    await toggleDone(t)
    closeSongModal()
  }
}

// 表单数据
const form = ref({
  title: '',
  description: '',
  url: '',
  priority: 2,
  due_date: '',
  tags: '',
})

const pendingTodos = computed(() =>
  todos.value
    .filter((t) => t.status === 'pending')
    .filter((t) => filterPriority.value === null || t.priority === filterPriority.value)
    .sort((a, b) => a.priority - b.priority)
)
const doneTodos = computed(() =>
  todos.value
    .filter((t) => t.status === 'done')
    .filter((t) => filterPriority.value === null || t.priority === filterPriority.value)
)

const priorityLabel = (p: number) => {
  const map: Record<number, string> = { 1: '高', 2: '中', 3: '低' }
  return map[p] || '中'
}
const priorityClass = (p: number) => `priority-${p}`

function resetForm() {
  form.value = { title: '', description: '', url: '', priority: 2, due_date: '', tags: '' }
  editingId.value = null
}

function openCreate() {
  resetForm()
  showForm.value = true
}

function openEdit(todo: Todo) {
  form.value = {
    title: todo.title,
    description: todo.description || '',
    url: todo.url || '',
    priority: todo.priority,
    due_date: todo.due_date ? todo.due_date.slice(0, 16) : '',
    tags: (todo.tags || []).join(', '),
  }
  editingId.value = todo.id
  showForm.value = true
}

async function loadTodos() {
  try {
    const { data } = await http.get<Todo[]>('/todos')
    todos.value = data
  } catch {
    todos.value = []
  }
}

async function submitForm() {
  if (!form.value.title.trim()) {
    msg.value = '标题不能为空'
    return
  }
  const payload = {
    ...form.value,
    tags: form.value.tags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean),
    due_date: form.value.due_date ? new Date(form.value.due_date).toISOString() : null,
  }
  try {
    if (editingId.value) {
      await http.put(`/todos/${editingId.value}`, payload)
    } else {
      await http.post('/todos', payload)
    }
    showForm.value = false
    resetForm()
    await loadTodos()
  } catch {
    msg.value = '保存失败'
  }
}

async function toggleDone(todo: Todo) {
  const newStatus = todo.status === 'done' ? 'pending' : 'done'
  const payload = {
    title: todo.title,
    description: todo.description,
    url: todo.url,
    source: todo.source,
    priority: todo.priority,
    due_date: todo.due_date,
    tags: todo.tags,
    status: newStatus,
    completed_at: newStatus === 'done' ? new Date().toISOString() : null,
  }
  try {
    await http.put(`/todos/${todo.id}`, payload)
    await loadTodos()
  } catch {
    msg.value = '操作失败'
  }
}

async function deleteTodo(todo: Todo) {
  if (!confirm(`删除「${todo.title}」？`)) return
  try {
    await http.delete(`/todos/${todo.id}`)
    await loadTodos()
  } catch {
    msg.value = '删除失败'
  }
}

async function toPlan(todo: Todo) {
  try {
    await http.post(`/todos/${todo.id}/to-plan`, { mark_done: false })
    msg.value = `已添加到今日计划：${todo.title}`
    setTimeout(() => (msg.value = ''), 3000)
  } catch {
    msg.value = '转计划失败'
  }
}

onMounted(loadTodos)
</script>

<template>
  <AppLayout>
    <template #title>待办事项</template>
    <template #actions>
      <button class="btn-primary" @click="openCreate">+ 新增待办</button>
    </template>

    <div v-if="msg" class="toast">{{ msg }}</div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="filter-group">
        <button
          :class="{ active: filterStatus === 'all' }"
          @click="filterStatus = 'all'"
        >全部</button>
        <button
          :class="{ active: filterStatus === 'pending' }"
          @click="filterStatus = 'pending'"
        >待办 ({{ pendingTodos.length }})</button>
        <button
          :class="{ active: filterStatus === 'done' }"
          @click="filterStatus = 'done'"
        >已完成 ({{ doneTodos.length }})</button>
      </div>
      <div class="filter-group">
        <span class="filter-label">优先级：</span>
        <button
          :class="{ active: filterPriority === null }"
          @click="filterPriority = null"
        >全部</button>
        <button
          :class="{ active: filterPriority === 1 }"
          @click="filterPriority = 1"
        >高</button>
        <button
          :class="{ active: filterPriority === 2 }"
          @click="filterPriority = 2"
        >中</button>
        <button
          :class="{ active: filterPriority === 3 }"
          @click="filterPriority = 3"
        >低</button>
      </div>
    </div>

    <!-- 新增/编辑表单 -->
    <div v-if="showForm" class="form-panel">
      <h3>{{ editingId ? '编辑待办' : '新增待办' }}</h3>
      <div class="form-row">
        <label>标题</label>
        <input v-model="form.title" type="text" placeholder="待办内容" maxlength="500" />
      </div>
      <div class="form-row">
        <label>描述</label>
        <textarea v-model="form.description" rows="3" placeholder="详细描述（可选）"></textarea>
      </div>
      <div class="form-row two-col">
        <div>
          <label>优先级</label>
          <select v-model="form.priority">
            <option :value="1">高</option>
            <option :value="2">中</option>
            <option :value="3">低</option>
          </select>
        </div>
        <div>
          <label>截止时间</label>
          <input v-model="form.due_date" type="datetime-local" />
        </div>
      </div>
      <div class="form-row">
        <label>链接</label>
        <input v-model="form.url" type="url" placeholder="相关链接（可选）" />
      </div>
      <div class="form-row">
        <label>标签</label>
        <input v-model="form.tags" type="text" placeholder="用逗号分隔，如：中医, 背诵" />
      </div>
      <div class="form-actions">
        <button class="btn-primary" @click="submitForm">保存</button>
        <button class="btn-ghost" @click="showForm = false; resetForm()">取消</button>
      </div>
    </div>

    <!-- 待办列表 -->
    <div v-if="filterStatus !== 'done' && pendingTodos.length" class="todo-section">
      <h3 class="section-title">待办 ({{ pendingTodos.length }})</h3>
      <div class="todo-list">
        <div v-for="todo in pendingTodos" :key="todo.id" class="todo-item">
          <input
            type="checkbox"
            :checked="todo.status === 'done'"
            @change="toggleDone(todo)"
          />
          <div class="todo-content">
            <div class="todo-title">
              <span v-if="todo.ref_type === 'formula_song'" class="todo-ref-icon" title="方歌复习">🎵</span>
              <span v-if="todo.ref_type === 'formula_song' && todo.ref_id" class="todo-link" title="点击查看方歌" @click="openFormulaSong(todo.ref_id)">{{ todo.title }}</span>
              <template v-else>{{ todo.title }}</template>
            </div>
            <div v-if="todo.description" class="todo-desc">{{ todo.description }}</div>
            <div class="todo-meta">
              <span class="priority-tag" :class="priorityClass(todo.priority)">
                {{ priorityLabel(todo.priority) }}
              </span>
              <span v-if="todo.due_date" class="meta-item">
                📅 {{ new Date(todo.due_date).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }}
              </span>
              <span v-if="todo.source === 'extension'" class="meta-item source-tag">扩展剪藏</span>
              <a v-if="todo.url" :href="todo.url" target="_blank" class="meta-item link">🔗 链接</a>
              <span v-for="tag in todo.tags" :key="tag" class="tag">{{ tag }}</span>
            </div>
          </div>
          <div class="todo-actions">
            <button class="icon-btn" title="转为今日计划" @click="toPlan(todo)">📅</button>
            <button class="icon-btn" title="编辑" @click="openEdit(todo)">✏️</button>
            <button class="icon-btn danger" title="删除" @click="deleteTodo(todo)">🗑️</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="filterStatus !== 'pending' && doneTodos.length" class="todo-section">
      <h3 class="section-title">已完成 ({{ doneTodos.length }})</h3>
      <div class="todo-list">
        <div v-for="todo in doneTodos" :key="todo.id" class="todo-item done">
          <input
            type="checkbox"
            :checked="todo.status === 'done'"
            @change="toggleDone(todo)"
          />
          <div class="todo-content">
            <div class="todo-title">
              <span v-if="todo.ref_type === 'formula_song'" class="todo-ref-icon" title="方歌复习">🎵</span>
              <span v-if="todo.ref_type === 'formula_song' && todo.ref_id" class="todo-link" title="点击查看方歌" @click="openFormulaSong(todo.ref_id)">{{ todo.title }}</span>
              <template v-else>{{ todo.title }}</template>
            </div>
            <div v-if="todo.description" class="todo-desc">{{ todo.description }}</div>
            <div class="todo-meta">
              <span v-if="todo.completed_at" class="meta-item">
                ✓ {{ new Date(todo.completed_at).toLocaleDateString('zh-CN') }}
              </span>
            </div>
          </div>
          <div class="todo-actions">
            <button class="icon-btn" title="编辑" @click="openEdit(todo)">✏️</button>
            <button class="icon-btn danger" title="删除" @click="deleteTodo(todo)">🗑️</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="!pendingTodos.length && !doneTodos.length" class="empty">
      <p>暂无待办，点击右上角「新增待办」开始</p>
    </div>
    <div v-else-if="filterStatus === 'pending' && !pendingTodos.length" class="empty">
      <p>没有待办事项 🎉</p>
    </div>
    <div v-else-if="filterStatus === 'done' && !doneTodos.length" class="empty">
      <p>暂无已完成事项</p>
    </div>

    <!-- 方歌弹窗 -->
    <div v-if="songModalOpen" class="song-overlay" @click.self="closeSongModal">
      <div class="song-modal">
        <div class="song-header">
          <h3>🎵 方歌详情</h3>
          <button class="song-close" @click="closeSongModal">×</button>
        </div>
        <div v-if="songLoading" class="song-loading">加载中…</div>
        <div v-else-if="currentSong" class="song-body">
          <div class="song-name">{{ currentSong.name }}</div>
          <pre class="song-text">{{ currentSong.song }}</pre>
          <div v-if="currentSong.related_formula" class="song-meta">
            <span class="meta-label">关联方剂：</span>{{ currentSong.related_formula }}
          </div>
          <div v-if="currentSong.notes" class="song-meta">
            <span class="meta-label">备注：</span>{{ currentSong.notes }}
          </div>
        </div>
        <div class="song-footer">
          <button class="btn-secondary" @click="closeSongModal">关闭</button>
          <button v-if="currentSong" class="btn-primary" @click="completeSongTodo(null)">✅ 完成此待办</button>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<style scoped>
.todo-link {
  color: var(--color-primary);
  cursor: pointer;
  border-bottom: 1px dashed var(--color-primary);
}
.todo-link:hover { opacity: 0.8; }
.song-overlay {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  background: rgba(0,0,0,0.5); z-index: 1000;
  display: flex; justify-content: center; align-items: center;
}
.song-modal {
  background: var(--bg-main); border-radius: 12px; padding: 0;
  width: 500px; max-width: 90vw; max-height: 80vh; display: flex; flex-direction: column;
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}
.song-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 18px; border-bottom: 1px solid var(--border-color);
}
.song-header h3 { margin: 0; font-size: 16px; }
.song-close {
  background: none; border: none; font-size: 24px; cursor: pointer;
  color: var(--text-secondary); line-height: 1;
}
.song-body { padding: 18px; overflow-y: auto; flex: 1; }
.song-loading { padding: 40px; text-align: center; color: var(--text-secondary); }
.song-name {
  font-size: 20px; font-weight: 600; margin-bottom: 12px;
  color: var(--text-primary);
}
.song-text {
  font-family: 'Cascadia Code', 'KaiTi', 'STKaiti', serif;
  font-size: 16px; line-height: 1.8;
  background: var(--bg-card); padding: 12px 14px; border-radius: 8px;
  margin: 0 0 12px; white-space: pre-wrap; color: var(--text-primary);
  border-left: 3px solid var(--color-primary);
}
.song-meta { margin-bottom: 6px; font-size: 14px; color: var(--text-secondary); }
.meta-label { font-weight: 500; color: var(--text-primary); }
.song-footer {
  display: flex; justify-content: flex-end; gap: 10px;
  padding: 12px 18px; border-top: 1px solid var(--border-color);
}
.song-footer .btn-primary, .song-footer .btn-secondary {
  padding: 8px 16px; border-radius: 6px; cursor: pointer; border: none;
}
.song-footer .btn-primary { background: var(--color-primary); color: white; }
.song-footer .btn-secondary { background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border-color); }
.toast {
  background: var(--color-primary);
  color: #fff;
  padding: 10px 16px;
  border-radius: var(--radius-sm);
  margin-bottom: 16px;
  font-size: 14px;
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 20px;
  padding: 12px 16px;
  background: var(--bg-card);
  border-radius: var(--radius);
  border: 1px solid var(--border-color);
}
.filter-group { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.filter-label { font-size: 13px; color: var(--text-secondary); }
.filter-group button {
  padding: 5px 12px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  background: var(--bg-main);
  color: var(--text-secondary);
  border: 1px solid transparent;
}
.filter-group button:hover { color: var(--text-primary); }
.filter-group button.active {
  background: var(--color-primary);
  color: #fff;
}

.form-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 24px;
}
.form-panel h3 { margin: 0 0 16px; font-size: 16px; }
.form-row { margin-bottom: 14px; }
.form-row label {
  display: block;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.form-row input, .form-row textarea, .form-row select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-main);
  color: var(--text-primary);
  font-size: 14px;
  box-sizing: border-box;
}
.form-row.two-col { display: flex; gap: 16px; }
.form-row.two-col > div { flex: 1; }
.form-actions { display: flex; gap: 10px; margin-top: 16px; }

.btn-primary {
  background: var(--color-primary);
  color: #fff;
  padding: 8px 18px;
  border-radius: var(--radius-sm);
  font-size: 14px;
}
.btn-primary:hover { opacity: 0.9; }
.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
  padding: 8px 18px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  border: 1px solid var(--border-color);
}
.btn-ghost:hover { color: var(--text-primary); }

.todo-section { margin-bottom: 24px; }
.section-title {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0 0 12px;
  font-weight: 600;
}

.todo-list { display: flex; flex-direction: column; gap: 8px; }
.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
}
.todo-item.done { opacity: 0.6; }
.todo-item.done .todo-title { text-decoration: line-through; }
.todo-item input[type="checkbox"] {
  margin-top: 3px;
  width: 18px;
  height: 18px;
  cursor: pointer;
}
.todo-content { flex: 1; min-width: 0; }
.todo-title { font-size: 15px; font-weight: 500; color: var(--text-primary); }
.todo-ref-icon { margin-right: 4px; }
.todo-desc { font-size: 13px; color: var(--text-secondary); margin-top: 4px; }
.todo-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  align-items: center;
}
.priority-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.priority-1 { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.priority-2 { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.priority-3 { background: rgba(107, 114, 128, 0.15); color: #6b7280; }
.meta-item { font-size: 12px; color: var(--text-secondary); }
.source-tag { color: var(--color-accent); }
.link { text-decoration: none; }
.link:hover { text-decoration: underline; }
.tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--bg-main);
  color: var(--text-secondary);
}

.todo-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}
.icon-btn {
  width: 30px;
  height: 30px;
  border-radius: var(--radius-sm);
  background: transparent;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.icon-btn:hover { background: var(--bg-main); }
.icon-btn.danger:hover { background: rgba(239, 68, 68, 0.1); }

.empty {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-secondary);
  font-size: 14px;
}
</style>
