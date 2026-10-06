<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { http } from '@/api/http'
import AppLayout from '@/components/AppLayout.vue'

interface WrongQuestion {
  id: number
  subject_id: number | null
  question_type: string | null
  content: string
  options: Record<string, string> | null
  answer: string | null
  analysis: string | null
  images: string[]
  correct_count: number
  wrong_count: number
  is_mastered: boolean
  ease_factor: number
  interval_days: number
  next_review_at: string | null
}

type Tab = 'list' | 'review'
const tab = ref<Tab>('list')

const questions = ref<WrongQuestion[]>([])
const subjects = ref<{ id: number; name: string; color: string }[]>([])
const showForm = ref(false)
const editingId = ref<number | null>(null)
const msg = ref('')
const ocrLoading = ref(false)

// 筛选/排序
const filterSubject = ref<number | null>(null)
const filterMastered = ref<string>('all') // all | true | false
const filterType = ref<string>('')
const sortBy = ref<string>('created_desc')
const searchQ = ref<string>('')

// 表单
const form = ref({
  subject_id: null as number | null,
  question_type: '',
  content: '',
  answer: '',
  analysis: '',
})

// 复习模式
const queue = ref<{ due: WrongQuestion[]; new: WrongQuestion[]; due_count: number; new_count: number }>({ due: [], new: [], due_count: 0, new_count: 0 })
const reviewList = ref<WrongQuestion[]>([])
const reviewIndex = ref(0)
const showAnswer = ref(false)
// 4 个评分按钮对应的下次复习时间描述（动态从后端 preview 接口获取）
const previewHints = ref<Record<string, string>>({ '1': '', '2': '', '3': '', '4': '' })

// 重复错题检测弹窗
const duplicateModal = ref(false)
const duplicateGroups = ref<{ similarity: number; a: DuplicateItem; b: DuplicateItem }[]>([])
const duplicateLoading = ref(false)

interface DuplicateItem {
  id: number
  subject_id: number | null
  question_type: string | null
  content: string
  answer: string | null
  is_mastered: boolean
  created_at: string | null
}

const currentCard = computed(() => reviewList.value[reviewIndex.value])
const reviewTotal = computed(() => reviewList.value.length)

function subjectName(id: number | null): string {
  if (!id) return ''
  const s = subjects.value.find((x) => x.id === id)
  return s ? s.name : ''
}

function resetForm() {
  form.value = { subject_id: null, question_type: '', content: '', answer: '', analysis: '' }
  editingId.value = null
}

async function loadQuestions() {
  try {
    const params: Record<string, any> = { sort: sortBy.value }
    if (filterSubject.value !== null) params.subject_id = filterSubject.value
    if (filterMastered.value !== 'all') params.is_mastered = filterMastered.value
    if (filterType.value) params.question_type = filterType.value
    if (searchQ.value.trim()) params.q = searchQ.value.trim()
    const { data } = await http.get<WrongQuestion[]>('/wrong-questions', { params })
    questions.value = data
  } catch {
    questions.value = []
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

async function loadQueue() {
  try {
    const { data } = await http.get('/wrong-questions/review/queue')
    queue.value = data
    reviewList.value = [...data.due, ...data.new]
    reviewIndex.value = 0
    showAnswer.value = false
    if (reviewList.value.length > 0) {
      loadPreviewHints(reviewList.value[0].id)
    } else {
      previewHints.value = { '1': '', '2': '', '3': '', '4': '' }
    }
  } catch {
    queue.value = { due: [], new: [], due_count: 0, new_count: 0 }
    reviewList.value = []
  }
}

async function loadPreviewHints(wqId: number) {
  // 重置为默认占位（避免上一张卡的描述残留）
  previewHints.value = { '1': '1 分钟后', '2': '约 1-3 天', '3': '约 3-7 天', '4': '约 7+ 天' }
  try {
    const { data } = await http.get<Record<string, string>>(`/wrong-questions/review/${wqId}/preview`)
    previewHints.value = data
  } catch {
    // 接口失败时保留默认占位
  }
}

async function loadDuplicates() {
  duplicateLoading.value = true
  duplicateModal.value = true
  try {
    const { data } = await http.get<{ total_groups: number; duplicates: typeof duplicateGroups.value }>(
      '/wrong-questions/duplicates'
    )
    duplicateGroups.value = data.duplicates
  } catch {
    duplicateGroups.value = []
    msg.value = '检测重复失败'
    setTimeout(() => (msg.value = ''), 2000)
  } finally {
    duplicateLoading.value = false
  }
}

async function deleteDuplicateItem(groupIndex: number, side: 'a' | 'b') {
  const group = duplicateGroups.value[groupIndex]
  if (!group) return
  const item = group[side]
  if (!confirm(`删除该错题？（ID: ${item.id}）`)) return
  try {
    await http.delete(`/wrong-questions/${item.id}`)
    // 删除后从列表移除该组
    duplicateGroups.value.splice(groupIndex, 1)
    if (tab.value === 'list') loadQuestions()
  } catch {
    msg.value = '删除失败'
    setTimeout(() => (msg.value = ''), 2000)
  }
}

async function submitForm() {
  if (!form.value.content.trim()) {
    msg.value = '题目内容不能为空'
    setTimeout(() => (msg.value = ''), 2000)
    return
  }
  const payload = {
    subject_id: form.value.subject_id,
    question_type: form.value.question_type || null,
    content: form.value.content,
    options: null,
    answer: form.value.answer || null,
    analysis: form.value.analysis || null,
    images: [],
  }
  try {
    if (editingId.value) {
      await http.put(`/wrong-questions/${editingId.value}`, payload)
    } else {
      await http.post('/wrong-questions', payload)
    }
    showForm.value = false
    resetForm()
    await loadQuestions()
  } catch {
    msg.value = '保存失败'
    setTimeout(() => (msg.value = ''), 2000)
  }
}

function openEdit(q: WrongQuestion) {
  form.value = {
    subject_id: q.subject_id,
    question_type: q.question_type || '',
    content: q.content,
    answer: q.answer || '',
    analysis: q.analysis || '',
  }
  editingId.value = q.id
  showForm.value = true
}

async function deleteQuestion(q: WrongQuestion) {
  if (!confirm(`删除错题？`)) return
  try {
    await http.delete(`/wrong-questions/${q.id}`)
    await loadQuestions()
  } catch {
    msg.value = '删除失败'
  }
}

/**
 * 解析 OCR 文本，提取题干、选项、答案、解析
 * 支持题库截图格式（如蓝基因、医考帮等）
 */
function parseOcrText(raw: string): { content: string; answer: string; analysis: string; questionType: string } {
  const lines = raw.split('\n').map((l) => l.trim()).filter((l) => l)

  const result = { content: '', answer: '', analysis: '', questionType: 'choice' }

  // 1. 识别题型
  const typeKeywords = ['单选题', '多选题', '判断题', '填空题', '简答题', 'A1型题', 'A2型题', 'B型题', 'X型题']
  let typeIdx = -1
  for (let i = 0; i < lines.length; i++) {
    if (typeKeywords.some((k) => lines[i].includes(k))) {
      typeIdx = i
      if (lines[i].includes('多选')) result.questionType = 'choice'
      else if (lines[i].includes('判断')) result.questionType = 'choice'
      else if (lines[i].includes('填空')) result.questionType = 'fill'
      else if (lines[i].includes('简答')) result.questionType = 'essay'
      else result.questionType = 'choice'
      break
    }
  }

  // 2. 识别选项行（A. B. C. D. E.）
  const optRegex = /^([A-E])[.．、\s]+(.+)$/
  const optionLines: { letter: string; text: string; idx: number }[] = []
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(optRegex)
    if (m) {
      optionLines.push({ letter: m[1], text: m[2], idx: i })
    }
  }

  // 3. 识别正确答案
  const ansRegex = /正确答案\s*[:：]?\s*([A-E])/
  let correctLetter = ''
  for (const l of lines) {
    const m = l.match(ansRegex)
    if (m) {
      correctLetter = m[1]
      break
    }
  }

  // 4. 提取题干（题型行之后、第一个选项之前，过滤干扰行）
  const noisePatterns = [/^\d+星$/, /^\d+\s*\/\s*\d+$/, /^第.+章/, /^第.+节/, /^难度/, /^答案/, /^易错/, /^统计/]
  let questionLines: string[] = []
  const startIdx = typeIdx >= 0 ? typeIdx + 1 : 0
  const endIdx = optionLines.length > 0 ? optionLines[0].idx : lines.length
  for (let i = startIdx; i < endIdx; i++) {
    if (noisePatterns.some((p) => p.test(lines[i]))) continue
    if (/^\d+(\.\d+)?%$/.test(lines[i])) continue // 正确率百分比
    questionLines.push(lines[i])
  }

  // 5. 组装 content = 题干 + 选项
  const contentParts: string[] = []
  if (questionLines.length) contentParts.push(questionLines.join('\n'))
  if (optionLines.length) {
    const opts = optionLines.map((o) => `${o.letter}. ${o.text}`).join('\n')
    contentParts.push(opts)
  }
  result.content = contentParts.join('\n')

  // 6. 组装 answer
  if (correctLetter) {
    const opt = optionLines.find((o) => o.letter === correctLetter)
    result.answer = opt ? `${correctLetter}. ${opt.text}` : correctLetter
  }

  // 7. 组装 analysis（易错点）
  const easyWrong = lines.find((l) => l.includes('易错'))
  if (easyWrong) {
    result.analysis = easyWrong
  }

  // 如果完全没解析出结构，回退到原始文本
  if (!result.content) {
    result.content = raw
  }

  return result
}

async function handleOcr(file: File) {
  ocrLoading.value = true
  msg.value = ''
  try {
    const fd = new FormData()
    fd.append('image', file)
    const { data } = await http.post('/wrong-questions/ocr', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    // 用后端 parsed 结构化字段（科目/题型/题目内容/答案）
    const parsed = data.parsed || {}
    form.value.content = parsed.content || data.text || ''
    form.value.answer = parsed.answer || ''
    form.value.question_type = parsed.question_type || ''
    if (parsed.subject_id) form.value.subject_id = parsed.subject_id
    msg.value = parsed.subject
      ? `识别完成：${parsed.subject}·${parsed.question_type || ''} 答案${parsed.answer || '-'}`
      : '识别完成，已自动填入'
    setTimeout(() => (msg.value = ''), 3000)
  } catch (e: any) {
    const detail = e.response?.data?.detail || 'OCR 识别失败'
    msg.value = detail
    setTimeout(() => (msg.value = ''), 4000)
  } finally {
    ocrLoading.value = false
  }
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) handleOcr(file)
  input.value = ''
}

async function submitReview(rating: number) {
  if (!currentCard.value) return
  try {
    await http.post(`/wrong-questions/review/${currentCard.value.id}`, { rating })
    reviewIndex.value++
    showAnswer.value = false
    if (reviewIndex.value >= reviewTotal.value) {
      await loadQueue()
    } else if (currentCard.value) {
      // 切换到下一张卡后，重新加载该卡的 preview 描述
      loadPreviewHints(currentCard.value.id)
    }
  } catch {
    msg.value = '提交失败'
    setTimeout(() => (msg.value = ''), 2000)
  }
}

onMounted(() => {
  loadQuestions()
  loadSubjects()
  loadQueue()
})

// 筛选/排序变化时自动重载
watch([filterSubject, filterMastered, filterType, sortBy], () => {
  loadQuestions()
})

// 搜索防抖
let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(searchQ, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => loadQuestions(), 400)
})
</script>

<template>
  <AppLayout>
    <template #title>错题本</template>
    <template #actions>
      <button class="btn-primary" @click="showForm = true; resetForm()">+ 录入错题</button>
    </template>

    <div v-if="msg" class="toast">{{ msg }}</div>

    <!-- 标签切换 -->
    <div class="tabs">
      <button :class="{ active: tab === 'list' }" @click="tab = 'list'">
        错题列表 ({{ questions.length }})
      </button>
      <button :class="{ active: tab === 'review' }" @click="tab = 'review'; loadQueue()">
        复习 ({{ queue.due_count + queue.new_count }})
      </button>
    </div>

    <!-- 列表模式 -->
    <div v-if="tab === 'list'">
      <!-- 筛选栏 -->
      <div class="filter-bar">
        <input v-model="searchQ" class="filter-input" placeholder="🔍 搜索题干/答案/解析..." />
        <select v-model="filterSubject" class="filter-select">
          <option :value="null">全部科目</option>
          <option v-for="s in subjects" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
        <select v-model="filterMastered" class="filter-select">
          <option value="all">全部状态</option>
          <option value="false">未掌握</option>
          <option value="true">已掌握</option>
        </select>
        <select v-model="filterType" class="filter-select">
          <option value="">全部题型</option>
          <option value="choice">选择题</option>
          <option value="fill">填空题</option>
          <option value="essay">简答题</option>
        </select>
        <select v-model="sortBy" class="filter-select">
          <option value="created_desc">最新优先</option>
          <option value="created_asc">最早优先</option>
          <option value="wrong_desc">错误次数最多</option>
          <option value="wrong_asc">错误次数最少</option>
        </select>
        <button class="filter-dup-btn" :disabled="duplicateLoading" @click="loadDuplicates">
          {{ duplicateLoading ? '🔍 检测中...' : '🔍 检测重复' }}
        </button>
      </div>

      <div v-if="questions.length" class="wq-list">
        <div v-for="q in questions" :key="q.id" class="wq-card" :class="{ mastered: q.is_mastered }">
          <div class="wq-header">
            <span v-if="subjectName(q.subject_id)" class="wq-subject" :style="{ color: subjects.find(s=>s.id===q.subject_id)?.color }">
              {{ subjectName(q.subject_id) }}
            </span>
            <span v-if="q.question_type" class="wq-type">{{ q.question_type }}</span>
            <span v-if="q.is_mastered" class="badge mastered">已掌握</span>
            <span class="wq-stats">✓{{ q.correct_count }} ✗{{ q.wrong_count }}</span>
          </div>
          <div class="wq-content">{{ q.content }}</div>
          <div v-if="q.answer" class="wq-answer">
            <strong>答案：</strong>{{ q.answer }}
          </div>
          <div v-if="q.analysis" class="wq-analysis">
            <strong>解析：</strong>{{ q.analysis }}
          </div>
          <div class="wq-actions">
            <button class="btn-ghost" @click="openEdit(q)">编辑</button>
            <button class="btn-ghost danger" @click="deleteQuestion(q)">删除</button>
          </div>
        </div>
      </div>
      <div v-else class="empty">暂无错题，点击「录入错题」开始</div>
    </div>

    <!-- 复习模式 -->
    <div v-if="tab === 'review'">
      <div v-if="reviewList.length === 0" class="empty">
        <p>没有需要复习的错题 🎉</p>
        <button class="btn-ghost" @click="loadQueue()">刷新队列</button>
      </div>
      <div v-else class="review-area">
        <div class="review-progress">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: Math.round((reviewIndex / reviewTotal) * 100) + '%' }"></div>
          </div>
          <span class="progress-text">{{ reviewIndex + 1 }} / {{ reviewTotal }}</span>
        </div>

        <div v-if="currentCard" class="review-card">
          <div class="card-header">
            <span v-if="subjectName(currentCard.subject_id)" class="card-subject">
              {{ subjectName(currentCard.subject_id) }}
            </span>
            <span class="card-type">{{ currentCard.question_type || '题目' }}</span>
            <span class="card-stats">✓{{ currentCard.correct_count }} ✗{{ currentCard.wrong_count }}</span>
          </div>
          <div class="card-content">{{ currentCard.content }}</div>

          <div v-if="showAnswer" class="card-answer-section">
            <div v-if="currentCard.answer" class="card-answer">
              <strong>答案：</strong>{{ currentCard.answer }}
            </div>
            <div v-if="currentCard.analysis" class="card-analysis">
              <strong>解析：</strong>{{ currentCard.analysis }}
            </div>
            <div class="rating-buttons">
              <button class="rate-btn r1" @click="submitReview(1)">❌ 不会
                <span class="rate-hint">{{ previewHints['1'] || '1 分钟后' }}</span>
              </button>
              <button class="rate-btn r2" @click="submitReview(2)">🤔 不确定
                <span class="rate-hint">{{ previewHints['2'] || '约 1-3 天' }}</span>
              </button>
              <button class="rate-btn r3" @click="submitReview(3)">✅ 会了
                <span class="rate-hint">{{ previewHints['3'] || '约 3-7 天' }}</span>
              </button>
              <button class="rate-btn r4" @click="submitReview(4)">🔥 很熟
                <span class="rate-hint">{{ previewHints['4'] || '约 7+ 天' }}</span>
              </button>
            </div>
          </div>
          <button v-else class="show-answer-btn" @click="showAnswer = true">显示答案</button>
        </div>
      </div>
    </div>

    <!-- 录入/编辑弹窗 -->
    <div v-if="showForm" class="modal-mask" @click.self="showForm = false; resetForm()">
      <div class="modal" @click.stop>
        <h3>{{ editingId ? '编辑错题' : '录入错题' }}</h3>

        <div class="form-row">
          <label>OCR 识别（拍照/上传图片）</label>
          <div class="ocr-row">
            <label class="ocr-btn" :class="{ loading: ocrLoading }">
              {{ ocrLoading ? '识别中...' : '📷 上传图片识别' }}
              <input type="file" accept="image/*" @change="onFileChange" hidden />
            </label>
          </div>
        </div>

        <div class="form-row two-col">
          <div>
            <label>科目</label>
            <select v-model="form.subject_id">
              <option :value="null">无科目</option>
              <option v-for="s in subjects" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </div>
          <div>
            <label>题型</label>
            <select v-model="form.question_type">
              <option value="">未分类</option>
              <option value="choice">选择题</option>
              <option value="fill">填空题</option>
              <option value="essay">简答题</option>
            </select>
          </div>
        </div>

        <div class="form-row">
          <label>题目内容</label>
          <textarea v-model="form.content" rows="4" placeholder="题目内容（OCR 识别后可编辑）"></textarea>
        </div>

        <div class="form-row">
          <label>答案</label>
          <textarea v-model="form.answer" rows="2" placeholder="正确答案"></textarea>
        </div>

        <div class="form-row">
          <label>解析</label>
          <textarea v-model="form.analysis" rows="3" placeholder="答案解析（可选）"></textarea>
        </div>

        <div class="modal-actions">
          <button class="btn-primary" @click="submitForm">保存</button>
          <button class="btn-ghost" @click="showForm = false; resetForm()">取消</button>
        </div>
      </div>
    </div>

    <!-- 重复错题检测弹窗 -->
    <div v-if="duplicateModal" class="modal-mask" @click.self="duplicateModal = false">
      <div class="modal dup-modal" @click.stop>
        <h3>🔍 重复错题检测</h3>
        <p class="dup-subtitle">
          共检测到 <strong>{{ duplicateGroups.length }}</strong> 组相似度 &gt; 95% 的错题对（基于最近 200 条）
        </p>

        <div v-if="duplicateLoading" class="dup-empty">检测中...</div>
        <div v-else-if="duplicateGroups.length === 0" class="dup-empty">未发现重复错题 🎉</div>

        <div v-else class="dup-list">
          <div v-for="(group, gi) in duplicateGroups" :key="gi" class="dup-group">
            <div class="dup-similarity">相似度 {{ (group.similarity * 100).toFixed(1) }}%</div>
            <div class="dup-pair">
              <div class="dup-item">
                <div class="dup-item-header">
                  <span v-if="subjectName(group.a.subject_id)" class="dup-subject">
                    {{ subjectName(group.a.subject_id) }}
                  </span>
                  <span v-if="group.a.question_type" class="dup-type">{{ group.a.question_type }}</span>
                  <span v-if="group.a.created_at" class="dup-date">{{ group.a.created_at.slice(0, 10) }}</span>
                </div>
                <div class="dup-content">{{ group.a.content.slice(0, 100) }}{{ group.a.content.length > 100 ? '...' : '' }}</div>
                <button class="btn-ghost danger dup-del" @click="deleteDuplicateItem(gi, 'a')">删除此项</button>
              </div>
              <div class="dup-vs">VS</div>
              <div class="dup-item">
                <div class="dup-item-header">
                  <span v-if="subjectName(group.b.subject_id)" class="dup-subject">
                    {{ subjectName(group.b.subject_id) }}
                  </span>
                  <span v-if="group.b.question_type" class="dup-type">{{ group.b.question_type }}</span>
                  <span v-if="group.b.created_at" class="dup-date">{{ group.b.created_at.slice(0, 10) }}</span>
                </div>
                <div class="dup-content">{{ group.b.content.slice(0, 100) }}{{ group.b.content.length > 100 ? '...' : '' }}</div>
                <button class="btn-ghost danger dup-del" @click="deleteDuplicateItem(gi, 'b')">删除此项</button>
              </div>
            </div>
          </div>
        </div>

        <div class="modal-actions">
          <button class="btn-ghost" @click="duplicateModal = false">关闭</button>
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

.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}
.tabs button {
  padding: 8px 18px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  background: var(--bg-card);
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
}
.tabs button.active {
  background: var(--color-primary);
  color: #fff;
  border-color: var(--color-primary);
}

.wq-list { display: flex; flex-direction: column; gap: 12px; }

/* 筛选栏 */
.filter-bar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  align-items: center;
}
.filter-input {
  flex: 1 1 auto;
  min-width: 120px;
  max-width: 280px;
  padding: 8px 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 14px;
}
.filter-select {
  flex: 0 0 auto;
  width: 110px;
  padding: 8px 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.filter-dup-btn {
  flex: 0 0 auto;
  padding: 8px 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
}
.filter-dup-btn:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.filter-dup-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.wq-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 16px;
}
.wq-card.mastered { opacity: 0.7; border-left: 3px solid #10b981; }
.wq-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.wq-subject {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--bg-main);
}
.wq-type {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--bg-main);
  color: var(--text-secondary);
}
.badge.mastered {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
}
.wq-stats { font-size: 12px; color: var(--text-secondary); margin-left: auto; }
.wq-content { font-size: 14px; line-height: 1.6; margin-bottom: 8px; white-space: pre-wrap; }
.wq-answer, .wq-analysis { font-size: 13px; color: var(--text-secondary); margin-top: 6px; }
.wq-actions { display: flex; gap: 8px; margin-top: 12px; }

.empty { text-align: center; padding: 60px 20px; color: var(--text-secondary); }

/* 复习模式 */
.review-area { max-width: 600px; margin: 0 auto; }
.review-progress { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
.progress-bar { flex: 1; height: 6px; background: var(--bg-main); border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--color-primary); transition: width 0.3s; }
.progress-text { font-size: 13px; color: var(--text-secondary); }

.review-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  padding: 24px;
}
.card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.card-subject { font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 10px; background: var(--bg-main); }
.card-type { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: var(--bg-main); color: var(--text-secondary); }
.card-stats { font-size: 12px; color: var(--text-secondary); margin-left: auto; }
.card-content { font-size: 16px; line-height: 1.7; margin-bottom: 20px; white-space: pre-wrap; }
.card-answer-section { border-top: 1px solid var(--border-color); padding-top: 16px; }
.card-answer, .card-analysis { font-size: 14px; margin-bottom: 12px; line-height: 1.6; }

.rating-buttons { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 16px; }
.rate-btn {
  padding: 12px 8px;
  border-radius: var(--radius-sm);
  font-size: 14px;
  font-weight: 500;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.rate-hint { font-size: 11px; opacity: 0.7; font-weight: normal; }
.rate-btn.r1 { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.rate-btn.r2 { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.rate-btn.r3 { background: rgba(59, 130, 246, 0.15); color: #3b82f6; }
.rate-btn.r4 { background: rgba(16, 185, 129, 0.15); color: #10b981; }
.rate-btn:hover { opacity: 0.85; transform: translateY(-1px); }

.show-answer-btn {
  width: 100%;
  padding: 14px;
  background: var(--color-primary);
  color: #fff;
  border-radius: var(--radius-sm);
  font-size: 15px;
}
.show-answer-btn:hover { opacity: 0.9; }

/* 弹窗 */
.modal-mask {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex; align-items: center; justify-content: center;
  z-index: 100;
  padding: 20px;
}
.modal {
  background: var(--bg-card);
  padding: 24px;
  border-radius: var(--radius);
  width: 100%;
  max-width: 560px;
  max-height: 90vh;
  overflow-y: auto;
}
.modal h3 { margin: 0 0 16px; }
.form-row { margin-bottom: 14px; }
.form-row label { display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }
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
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 16px; }

.ocr-row { display: flex; gap: 10px; }
.ocr-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 10px 20px;
  background: var(--color-accent);
  color: #fff;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 14px;
}
.ocr-btn:hover { opacity: 0.9; }
.ocr-btn.loading { opacity: 0.6; cursor: not-allowed; }

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
.btn-ghost.danger:hover { color: #ef4444; border-color: #ef4444; }

/* 重复错题检测弹窗 */
.dup-modal { max-width: 720px; }
.dup-subtitle { font-size: 13px; color: var(--text-secondary); margin: -8px 0 16px; }
.dup-subtitle strong { color: var(--color-primary); }
.dup-empty { text-align: center; padding: 40px 20px; color: var(--text-secondary); }
.dup-list { display: flex; flex-direction: column; gap: 12px; }
.dup-group {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 12px;
  background: var(--bg-main);
}
.dup-similarity {
  font-size: 12px;
  font-weight: 600;
  color: #f59e0b;
  margin-bottom: 8px;
}
.dup-pair { display: flex; gap: 8px; align-items: stretch; }
.dup-item {
  flex: 1;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.dup-vs {
  display: flex;
  align-items: center;
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 600;
}
.dup-item-header { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.dup-subject { font-size: 11px; font-weight: 600; padding: 2px 6px; border-radius: 8px; background: var(--bg-main); }
.dup-type { font-size: 10px; padding: 2px 6px; border-radius: 8px; background: var(--bg-main); color: var(--text-secondary); }
.dup-date { font-size: 10px; color: var(--text-secondary); margin-left: auto; }
.dup-content { font-size: 13px; line-height: 1.5; white-space: pre-wrap; flex: 1; }
.dup-del { align-self: flex-start; padding: 4px 10px; font-size: 12px; }
</style>
