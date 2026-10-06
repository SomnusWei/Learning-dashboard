<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { http } from '@/api/http'
import AppLayout from '@/components/AppLayout.vue'

interface PlanItem {
  id: string
  title: string
  description: string
  subject_id: number | null
  url: string
  done: boolean
  source: string
  type: string      // manual | formula | acupoint | herb | wrong_question | morning_reading
  target: number    // 目标数量
  current: number   // 当前进度
}

interface DaySummary {
  date: string
  total: number
  done: number
}

interface Template {
  id: number
  name: string
  description: string | null
  items: PlanItem[]
}

const today = new Date()
const viewYear = ref(today.getFullYear())
const viewMonth = ref(today.getMonth() + 1)
const selectedDate = ref(formatDate(today))
const monthDays = ref<DaySummary[]>([])
const planItems = ref<PlanItem[]>([])
const subjects = ref<{ id: number; name: string; color: string }[]>([])
const templates = ref<Template[]>([])

// 预置模板类型配置
const PRESET_TYPES = [
  { key: 'wrong_question', label: '复习错题库', icon: '❌', defaultCount: 20, hint: '随机抽取未掌握的错题进行复习' },
]

// 快速创建模板弹窗
const showPresetModal = ref(false)
const presetForm = ref<Record<string, number>>({
  wrong_question: 20,
})

// 学习卡片弹窗状态
const studyItem = ref<PlanItem | null>(null)
const studyCard = ref<any>(null)
const studyLoading = ref(false)
const studyComplete = ref(false)

// 新增表单
const newItem = ref({
  title: '',
  description: '',
  subject_id: null as number | null,
})
const msg = ref('')

// 模板保存弹窗
const showSaveTpl = ref(false)
const tplName = ref('')

function formatDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const monthLabel = computed(() => `${viewYear.value} 年 ${viewMonth.value} 月`)

// 生成月历网格（6 周 x 7 天）
const calendarGrid = computed(() => {
  const first = new Date(viewYear.value, viewMonth.value - 1, 1)
  const startWeekday = first.getDay() // 0=周日
  const daysInMonth = new Date(viewYear.value, viewMonth.value, 0).getDate()
  const cells: { date: string | null; day: number; inMonth: boolean }[] = []

  // 前置空白
  for (let i = 0; i < startWeekday; i++) {
    cells.push({ date: null, day: 0, inMonth: false })
  }
  // 当月日期
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({
      date: formatDate(new Date(viewYear.value, viewMonth.value - 1, d)),
      day: d,
      inMonth: true,
    })
  }
  // 后置填充到 42 格
  while (cells.length < 42) {
    cells.push({ date: null, day: 0, inMonth: false })
  }
  return cells
})

function getDaySummary(dateStr: string): DaySummary | undefined {
  return monthDays.value.find((d) => d.date === dateStr)
}

async function loadMonth() {
  try {
    const { data } = await http.get(`/plans/monthly/${viewYear.value}/${viewMonth.value}`)
    monthDays.value = data.days
  } catch {
    monthDays.value = []
  }
}

async function loadSubjects() {
  try {
    const { data } = await http.get('/subjects')
    subjects.value = data
  } catch {
    subjects.value = []
  }
}

async function loadTemplates() {
  try {
    const { data } = await http.get('/plans/templates')
    templates.value = data
  } catch {
    templates.value = []
  }
}

async function loadDaily() {
  try {
    const { data } = await http.get(`/plans/daily/${selectedDate.value}`)
    planItems.value = (data.items || []).map((it: any) => {
      // 推断类型：从标题匹配预置模板关键词
      let type = it.type || ''
      if (!type || type === 'manual') {
        if (it.title?.includes('错题')) type = 'wrong_question'
        else type = 'manual'
      }
      // 从标题中提取数量（如 "背诵方剂 10 个" → 10）
      let target = it.target ?? 0
      if (!target) {
        const m = it.title?.match(/(\d+)\s*个/)
        if (m) target = parseInt(m[1], 10)
        else target = 1
      }
      return {
        ...it,
        type,
        target,
        current: it.current ?? 0,
      }
    })
  } catch {
    planItems.value = []
  }
}

function selectDate(dateStr: string) {
  selectedDate.value = dateStr
  loadDaily()
}

function prevMonth() {
  if (viewMonth.value === 1) {
    viewMonth.value = 12
    viewYear.value--
  } else {
    viewMonth.value--
  }
}

function nextMonth() {
  if (viewMonth.value === 12) {
    viewMonth.value = 1
    viewYear.value++
  } else {
    viewMonth.value++
  }
}

function goToday() {
  viewYear.value = today.getFullYear()
  viewMonth.value = today.getMonth() + 1
  selectedDate.value = formatDate(today)
}

async function addItem() {
  if (!newItem.value.title.trim()) return
  try {
    await http.post(`/plans/daily/item?plan_date=${selectedDate.value}`, {
      title: newItem.value.title,
      description: newItem.value.description,
      subject_id: newItem.value.subject_id,
      source: 'manual',
    })
    newItem.value = { title: '', description: '', subject_id: null }
    await loadDaily()
    await loadMonth()
  } catch {
    msg.value = '添加失败'
    setTimeout(() => (msg.value = ''), 2000)
  }
}

async function toggleItem(item: PlanItem) {
  try {
    await http.put(
      `/plans/daily/item/${item.id}?plan_date=${selectedDate.value}`,
      { done: !item.done }
    )
    await loadDaily()
    await loadMonth()
  } catch {
    msg.value = '更新失败'
    setTimeout(() => (msg.value = ''), 2000)
  }
}

async function deleteItem(item: PlanItem) {
  if (!confirm(`删除「${item.title}」？`)) return
  try {
    await http.delete(`/plans/daily/item/${item.id}?plan_date=${selectedDate.value}`)
    await loadDaily()
    await loadMonth()
  } catch {
    msg.value = '删除失败'
    setTimeout(() => (msg.value = ''), 2000)
  }
}

async function saveAsTemplate() {
  if (!tplName.value.trim()) return
  try {
    await http.post('/plans/template', {
      name: tplName.value,
      items: planItems.value.map((it) => ({
        title: it.title,
        description: it.description,
        subject_id: it.subject_id,
        url: it.url,
        source: it.source,
        type: it.type,
        target: it.target,
        current: 0,
      })),
    })
    showSaveTpl.value = false
    tplName.value = ''
    await loadTemplates()
    msg.value = '模板已保存'
    setTimeout(() => (msg.value = ''), 2000)
  } catch {
    msg.value = '保存失败'
    setTimeout(() => (msg.value = ''), 2000)
  }
}

async function applyTemplate(tpl: Template) {
  if (!confirm(`将模板「${tpl.name}」应用到 ${selectedDate.value}？`)) return
  try {
    await http.post(`/plans/template/${tpl.id}/apply`, { plan_date: selectedDate.value })
    await loadDaily()
    await loadMonth()
    msg.value = '模板已应用'
    setTimeout(() => (msg.value = ''), 2000)
  } catch {
    msg.value = '应用失败'
    setTimeout(() => (msg.value = ''), 2000)
  }
}

// 点击学习：增加进度
async function addProgress(item: PlanItem, delta: number = 1) {
  try {
    await http.post(
      `/plans/daily/item/${item.id}/progress?plan_date=${selectedDate.value}`,
      { delta }
    )
    await loadDaily()
    await loadMonth()
  } catch {
    msg.value = '更新失败'
    setTimeout(() => (msg.value = ''), 2000)
  }
}

// 计算单项进度百分比
function itemRate(item: PlanItem): number {
  if (!item.target || item.target <= 0) return item.done ? 100 : 0
  return Math.min(100, Math.round((item.current / item.target) * 100))
}

// ===== 学习卡片弹窗 =====
async function fetchCard(type: string) {
  studyLoading.value = true
  try {
    const { data } = await http.get('/plans/study-card', { params: { type } })
    studyCard.value = data
  } catch {
    studyCard.value = { name: '加载失败', fields: { 说明: '请检查网络或稍后重试' }, is_placeholder: true }
  } finally {
    studyLoading.value = false
  }
}

async function openStudy(item: PlanItem) {
  studyItem.value = { ...item }
  studyComplete.value = false
  await fetchCard(item.type)
}

function closeStudy() {
  studyItem.value = null
  studyCard.value = null
  studyComplete.value = false
}

async function nextCard() {
  if (!studyItem.value) return
  // 先增加进度
  const newCurrent = Math.min(studyItem.value.current + 1, studyItem.value.target)
  studyItem.value.current = newCurrent
  try {
    await http.post(
      `/plans/daily/item/${studyItem.value.id}/progress?plan_date=${selectedDate.value}`,
      { delta: 1 }
    )
  } catch {
    msg.value = '进度更新失败'
    setTimeout(() => (msg.value = ''), 2000)
  }

  // 判断是否完成
  if (newCurrent >= studyItem.value.target) {
    studyItem.value.done = true
    studyComplete.value = true
    await loadDaily()
    await loadMonth()
    // 3 秒后自动关闭
    setTimeout(() => closeStudy(), 2500)
    return
  }

  // 继续下一张卡片
  await fetchCard(studyItem.value.type)
}

// 应用预置模板（直接添加到当日计划）
async function applyPreset() {
  const items = PRESET_TYPES.filter((p) => presetForm.value[p.key] > 0).map((p) => ({
    title: `${p.icon} ${p.label} ${presetForm.value[p.key]} 个`,
    description: p.hint,
    source: 'template',
    type: p.key,
    target: presetForm.value[p.key],
    current: 0,
  }))
  if (!items.length) {
    msg.value = '请至少设置一项数量'
    setTimeout(() => (msg.value = ''), 2000)
    return
  }
  try {
    for (const it of items) {
      await http.post(`/plans/daily/item?plan_date=${selectedDate.value}`, it)
    }
    showPresetModal.value = false
    await loadDaily()
    await loadMonth()
    msg.value = `已添加 ${items.length} 项学习任务`
    setTimeout(() => (msg.value = ''), 2000)
  } catch {
    msg.value = '添加失败'
    setTimeout(() => (msg.value = ''), 2000)
  }
}

async function deleteTemplate(tpl: Template) {
  if (!confirm(`删除模板「${tpl.name}」？`)) return
  try {
    await http.delete(`/plans/template/${tpl.id}`)
    await loadTemplates()
  } catch {
    msg.value = '删除失败'
    setTimeout(() => (msg.value = ''), 2000)
  }
}

function subjectName(id: number | null): string {
  if (!id) return ''
  const s = subjects.value.find((x) => x.id === id)
  return s ? s.name : ''
}

const dailyProgress = computed(() => {
  const total = planItems.value.length
  const done = planItems.value.filter((i) => i.done).length
  return { total, done, rate: total ? Math.round((done / total) * 100) : 0 }
})

watch([viewYear, viewMonth], () => {
  loadMonth()
})

onMounted(() => {
  loadMonth()
  loadSubjects()
  loadTemplates()
  loadDaily()
})
</script>

<template>
  <AppLayout>
    <template #title>学习计划</template>
    <template #actions>
      <button class="btn-ghost" @click="goToday">今天</button>
    </template>

    <div v-if="msg" class="toast">{{ msg }}</div>

    <!-- 月历视图 -->
    <div class="calendar-panel">
      <div class="calendar-header">
        <button class="nav-btn" @click="prevMonth">‹</button>
        <h2>{{ monthLabel }}</h2>
        <button class="nav-btn" @click="nextMonth">›</button>
      </div>
      <div class="weekday-row">
        <div v-for="w in ['日','一','二','三','四','五','六']" :key="w" class="weekday">{{ w }}</div>
      </div>
      <div class="calendar-grid">
        <div
          v-for="(cell, idx) in calendarGrid"
          :key="idx"
          class="calendar-day"
          :class="{
            'other-month': !cell.inMonth,
            'selected': cell.date === selectedDate,
            'today': cell.date === formatDate(today),
            'has-plan': cell.inMonth && getDaySummary(cell.date!)?.total,
          }"
          @click="cell.inMonth && selectDate(cell.date!)"
        >
          <span v-if="cell.inMonth" class="day-num">{{ cell.day }}</span>
          <div v-if="cell.inMonth" class="day-progress">
            <template v-if="getDaySummary(cell.date!)">
              <div class="progress-dots">
                <span
                  v-for="n in getDaySummary(cell.date!)!.total"
                  :key="n"
                  class="dot"
                  :class="{ done: n <= getDaySummary(cell.date!)!.done }"
                ></span>
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- 日计划详情 -->
    <div class="daily-panel">
      <div class="daily-header">
        <h3>{{ selectedDate }} 计划</h3>
        <span class="progress-text">{{ dailyProgress.done }}/{{ dailyProgress.total }} ({{ dailyProgress.rate }}%)</span>
        <button class="btn-primary" @click="showPresetModal = true">⚡ 快速模板</button>
        <button class="btn-ghost" @click="showSaveTpl = true">💾 存为模板</button>
      </div>

      <!-- 进度条 -->
      <div class="daily-progress-bar">
        <div class="progress-fill" :style="{ width: dailyProgress.rate + '%' }"></div>
      </div>

      <!-- 新增项 -->
      <div class="add-item">
        <input
          v-model="newItem.title"
          type="text"
          placeholder="添加计划项..."
          @keyup.enter="addItem"
        />
        <select v-model="newItem.subject_id" class="subject-select">
          <option :value="null">无科目</option>
          <option v-for="s in subjects" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
        <button class="btn-primary" @click="addItem">添加</button>
      </div>

      <!-- 计划项列表 -->
      <div v-if="planItems.length" class="item-list">
        <div
          v-for="item in planItems"
          :key="item.id"
          class="plan-item"
          :class="{ done: item.done }"
        >
          <input
            type="checkbox"
            :checked="item.done"
            @change="toggleItem(item)"
          />
          <div class="item-content">
            <span class="item-title">{{ item.title }}</span>
            <span v-if="subjectName(item.subject_id)" class="item-subject" :style="{ color: subjects.find(s=>s.id===item.subject_id)?.color }">
              {{ subjectName(item.subject_id) }}
            </span>
            <span v-if="item.source === 'template'" class="item-source">模板</span>
            <span v-else-if="item.source === 'todo'" class="item-source todo">待办</span>

            <!-- 交互式进度条（非 manual 类型） -->
            <div v-if="item.type && item.type !== 'manual' && item.target > 0" class="item-progress">
              <div class="item-progress-bar">
                <div class="item-progress-fill" :style="{ width: itemRate(item) + '%' }"></div>
              </div>
              <span class="item-progress-text">{{ item.current }}/{{ item.target }}</span>
              <button
                class="study-btn"
                :disabled="item.done"
                @click="openStudy(item)"
              >
                {{ item.done ? '✓ 已完成' : '📖 开始学习' }}
              </button>
            </div>
          </div>
          <button class="icon-btn danger" @click="deleteItem(item)">🗑️</button>
        </div>
      </div>
      <div v-else class="empty">暂无计划，添加一项开始吧</div>

      <!-- 模板区 -->
      <div v-if="templates.length" class="templates">
        <h4>快速模板</h4>
        <div class="template-list">
          <div v-for="tpl in templates" :key="tpl.id" class="template-card">
            <div class="tpl-info">
              <span class="tpl-name">{{ tpl.name }}</span>
              <span class="tpl-count">{{ tpl.items.length }} 项</span>
            </div>
            <div class="tpl-actions">
              <button class="btn-ghost" @click="applyTemplate(tpl)">应用</button>
              <button class="icon-btn danger" @click="deleteTemplate(tpl)">🗑️</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 保存模板弹窗 -->
    <div v-if="showSaveTpl" class="modal-mask" @click.self="showSaveTpl = false">
      <div class="modal">
        <h3>保存为模板</h3>
        <input v-model="tplName" type="text" placeholder="模板名称" />
        <div class="modal-actions">
          <button class="btn-primary" @click="saveAsTemplate">保存</button>
          <button class="btn-ghost" @click="showSaveTpl = false">取消</button>
        </div>
      </div>
    </div>

    <!-- 快速模板弹窗 -->
    <div v-if="showPresetModal" class="modal-mask" @click.self="showPresetModal = false">
      <div class="modal modal-lg">
        <h3>⚡ 快速创建学习模板</h3>
        <p class="modal-hint">设置每日各类学习任务的数量，自动添加到当日计划。设置为 0 则不添加该项。</p>
        <div class="preset-list">
          <div v-for="p in PRESET_TYPES" :key="p.key" class="preset-row">
            <span class="preset-icon">{{ p.icon }}</span>
            <div class="preset-info">
              <span class="preset-label">{{ p.label }}</span>
              <span class="preset-hint">{{ p.hint }}</span>
            </div>
            <input
              v-model.number="presetForm[p.key]"
              type="number"
              min="0"
              class="preset-count"
            />
            <span class="preset-unit">个/天</span>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-primary" @click="applyPreset">添加到今日计划</button>
          <button class="btn-ghost" @click="showPresetModal = false">取消</button>
        </div>
      </div>
    </div>

    <!-- 学习卡片弹窗 -->
    <div v-if="studyItem" class="modal-mask" @click.self="closeStudy">
      <div class="modal study-modal">
        <div class="study-header">
          <h3>{{ studyItem.title }}</h3>
          <span class="study-progress">{{ studyItem.current }}/{{ studyItem.target }}</span>
        </div>

        <div v-if="studyLoading" class="study-loading">加载中...</div>

        <div v-else-if="studyCard" class="study-card-content">
          <h4 class="card-name">{{ studyCard.name }}</h4>
          <div v-if="studyCard.is_placeholder" class="card-placeholder">
            <p>{{ Object.values(studyCard.fields)[0] }}</p>
          </div>
          <div v-else class="card-fields">
            <div v-for="(val, key) in studyCard.fields" :key="key" class="card-field">
              <span class="field-key">{{ key }}</span>
              <span class="field-val">{{ val }}</span>
            </div>
          </div>
        </div>

        <div class="study-actions">
          <button class="btn-ghost" @click="closeStudy">关闭</button>
          <button class="btn-primary" @click="nextCard" :disabled="studyLoading">
            下一个 →
          </button>
        </div>
        <div v-if="studyComplete" class="study-complete-msg">
          🎉 今日任务已完成！
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<style scoped>
.toast {
  background: var(--color-primary);
  color: #fff;
  padding: 10px 16px;
  border-radius: var(--radius-sm);
  margin-bottom: 16px;
  font-size: 14px;
}

.calendar-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 20px;
}
.calendar-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
  margin-bottom: 16px;
}
.calendar-header h2 { margin: 0; font-size: 18px; }
.nav-btn {
  width: 36px; height: 36px;
  border-radius: 50%;
  font-size: 20px;
  background: var(--bg-main);
  color: var(--text-primary);
}
.nav-btn:hover { background: var(--color-primary); color: #fff; }

.weekday-row {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
  margin-bottom: 4px;
}
.weekday {
  text-align: center;
  font-size: 12px;
  color: var(--text-secondary);
  padding: 6px 0;
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
}
.calendar-day {
  min-height: 72px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  background: var(--bg-main);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  transition: all 0.15s;
}
.calendar-day:hover:not(.other-month) { background: var(--bg-card); border: 1px solid var(--color-primary); }
.calendar-day.other-month { opacity: 0.3; cursor: default; }
.calendar-day.today .day-num {
  background: var(--color-primary);
  color: #fff;
  border-radius: 50%;
  width: 22px; height: 22px;
  display: flex; align-items: center; justify-content: center;
}
.calendar-day.selected { border: 2px solid var(--color-primary); background: var(--bg-card); }
.day-num { font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.day-progress { flex: 1; display: flex; align-items: flex-end; }
.progress-dots { display: flex; flex-wrap: wrap; gap: 2px; justify-content: center; }
.dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--border-color);
}
.dot.done { background: var(--color-primary); }

.daily-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 20px;
}
.daily-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.daily-header h3 { margin: 0; font-size: 16px; flex: 1; }
.progress-text { font-size: 13px; color: var(--text-secondary); }

.daily-progress-bar {
  height: 6px;
  background: var(--bg-main);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 16px;
}
.progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.3s;
}

.add-item {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.add-item input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-main);
  color: var(--text-primary);
  font-size: 14px;
}
.subject-select {
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-main);
  color: var(--text-primary);
  font-size: 14px;
}

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
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  border: 1px solid var(--border-color);
}
.btn-ghost:hover { color: var(--text-primary); }

.item-list { display: flex; flex-direction: column; gap: 8px; }
.plan-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: var(--bg-main);
  border-radius: var(--radius-sm);
}
.plan-item.done .item-title { text-decoration: line-through; opacity: 0.6; }
.plan-item input[type="checkbox"] { width: 18px; height: 18px; cursor: pointer; }
.item-content { flex: 1; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.item-title { font-size: 14px; }
.item-subject {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--bg-card);
  font-weight: 600;
}
.item-source {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(107, 114, 128, 0.15);
  color: #6b7280;
}
.item-source.todo { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }

/* 交互式学习进度 */
.item-progress {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  margin-top: 8px;
}
.item-progress-bar {
  flex: 1;
  height: 8px;
  background: var(--bg-card);
  border-radius: 4px;
  overflow: hidden;
}
.item-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary), #34d399);
  border-radius: 4px;
  transition: width 0.3s;
}
.item-progress-text {
  font-size: 12px;
  color: var(--text-secondary);
  min-width: 50px;
  text-align: right;
}
.study-btn {
  padding: 4px 14px;
  background: var(--color-primary);
  color: #fff;
  border-radius: var(--radius-sm);
  font-size: 13px;
  white-space: nowrap;
}
.study-btn.small { padding: 4px 10px; font-size: 12px; }
.study-btn:hover { opacity: 0.9; }
.study-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.icon-btn {
  width: 30px; height: 30px;
  border-radius: var(--radius-sm);
  background: transparent;
  font-size: 14px;
  display: flex; align-items: center; justify-content: center;
}
.icon-btn:hover { background: var(--bg-card); }
.icon-btn.danger:hover { background: rgba(239, 68, 68, 0.1); }

.empty {
  text-align: center;
  padding: 30px;
  color: var(--text-secondary);
  font-size: 14px;
}

.templates { margin-top: 24px; border-top: 1px solid var(--border-color); padding-top: 16px; }
.templates h4 { margin: 0 0 12px; font-size: 14px; color: var(--text-secondary); }
.template-list { display: flex; flex-wrap: wrap; gap: 10px; }
.template-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: var(--bg-main);
  border-radius: var(--radius-sm);
}
.tpl-info { display: flex; flex-direction: column; }
.tpl-name { font-size: 14px; font-weight: 500; }
.tpl-count { font-size: 11px; color: var(--text-secondary); }
.tpl-actions { display: flex; gap: 6px; }

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal {
  background: var(--bg-card);
  padding: 24px;
  border-radius: var(--radius);
  width: 90%;
  max-width: 400px;
}
.modal h3 { margin: 0 0 16px; }
.modal input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-main);
  color: var(--text-primary);
  font-size: 14px;
  box-sizing: border-box;
  margin-bottom: 16px;
}
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; }

.modal-lg { max-width: 520px; }
.modal-hint { font-size: 13px; color: var(--text-secondary); margin: 0 0 16px; line-height: 1.5; }
.preset-list { display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px; }
.preset-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--bg-main);
  border-radius: var(--radius-sm);
}
.preset-icon { font-size: 22px; }
.preset-info { flex: 1; display: flex; flex-direction: column; }
.preset-label { font-size: 14px; font-weight: 500; }
.preset-hint { font-size: 11px; color: var(--text-secondary); }
.preset-count {
  width: 70px;
  padding: 6px 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 14px;
  text-align: center;
}
.preset-unit { font-size: 12px; color: var(--text-secondary); min-width: 40px; }

/* 学习卡片弹窗 */
.study-modal { max-width: 600px; }
.study-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.study-header h3 { margin: 0; font-size: 18px; }
.study-progress {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-primary);
  background: rgba(91, 141, 239, 0.1);
  padding: 4px 12px;
  border-radius: 12px;
}
.study-loading {
  text-align: center;
  padding: 60px 0;
  color: var(--text-secondary);
  font-size: 14px;
}
.study-card-content {
  min-height: 300px;
  padding: 8px 0;
}
.card-name {
  font-size: 20px;
  margin: 0 0 16px;
  padding-bottom: 12px;
  border-bottom: 2px solid var(--color-primary);
}
.card-placeholder {
  padding: 40px 20px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 15px;
  line-height: 1.8;
}
.card-fields { display: flex; flex-direction: column; gap: 12px; }
.card-field {
  display: flex;
  gap: 12px;
  padding: 10px 14px;
  background: var(--bg-main);
  border-radius: var(--radius-sm);
}
.field-key {
  font-weight: 600;
  color: var(--color-primary);
  min-width: 70px;
  font-size: 13px;
  flex-shrink: 0;
}
.field-val {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary);
  word-break: break-word;
}
.study-actions {
  display: flex;
  justify-content: space-between;
  margin-top: 20px;
  gap: 12px;
}
.study-complete-msg {
  text-align: center;
  margin-top: 16px;
  font-size: 16px;
  font-weight: 600;
  color: #10b981;
  padding: 12px;
  background: rgba(16, 185, 129, 0.1);
  border-radius: var(--radius-sm);
}
</style>
