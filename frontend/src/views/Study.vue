<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { http } from '@/api/http'
import AppLayout from '@/components/AppLayout.vue'
import { FormulaSongAPI, type FormulaSong, type FormulaSongIn } from '@/api/formulaSongs'

const route = useRoute()
const libraries = ref<any[]>([])
const cards = ref<any[]>([])
const activeLib = ref<number | null>(null)
const focusCardId = ref<number | null>(null)

// 复习模式
type Tab = 'browse' | 'review' | 'songs'
const tab = ref<Tab>('browse')
const queue = ref<{ due: any[]; new: any[] }>({ due: [], new: [] })
const reviewList = ref<any[]>([])
const reviewIndex = ref(0)
const showAnswer = ref(false)
const reviewMsg = ref('')

// 复习计时
const reviewSeconds = ref(0)
let timer: ReturnType<typeof setInterval> | null = null
let lastReported = 0

const currentCard = computed(() => reviewList.value[reviewIndex.value])
const reviewTotal = computed(() => reviewList.value.length)
const reviewProgress = computed(() =>
  reviewTotal.value === 0 ? 0 : Math.round((reviewIndex.value / reviewTotal.value) * 100)
)
const reviewTimeText = computed(() => {
  const m = Math.floor(reviewSeconds.value / 60)
  const s = reviewSeconds.value % 60
  return `${m}:${s.toString().padStart(2, '0')}`
})

function startTimer() {
  stopTimer()
  timer = setInterval(() => {
    reviewSeconds.value++
    // 每 30 秒上报一次
    if (reviewSeconds.value - lastReported >= 30) {
      flushDuration()
    }
  }, 1000)
}

function stopTimer() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

async function flushDuration() {
  const delta = reviewSeconds.value - lastReported
  if (delta <= 0) return
  lastReported = reviewSeconds.value
  try {
    await http.patch('/study/log/duration', { seconds: delta })
  } catch {
    // 上报失败不影响学习
  }
}

// 切换到复习模式时启动计时，切走时停止并上报
watch(tab, (v) => {
  if (v === 'review') {
    reviewSeconds.value = 0
    lastReported = 0
    startTimer()
  } else {
    stopTimer()
    flushDuration()
  }
})

onUnmounted(() => {
  stopTimer()
  flushDuration()
})

async function loadLibraries() {
  try {
    const { data } = await http.get('/knowledge-base/libraries')
    libraries.value = data
  } catch {
    libraries.value = []
  }
}

async function loadCards(libId: number) {
  activeLib.value = libId
  try {
    const { data } = await http.get(`/knowledge-base/${libId}/cards`)
    cards.value = data
  } catch {
    cards.value = []
  }
}

async function loadQueue() {
  try {
    const { data } = await http.get('/study/queue')
    queue.value = data
    // 组合复习列表：先 due 再 new
    reviewList.value = [...data.due, ...data.new]
    reviewIndex.value = 0
    showAnswer.value = false
    reviewMsg.value = ''
  } catch {
    queue.value = { due: [], new: [] }
    reviewList.value = []
  }
}

async function submitReview(rating: number) {
  if (!currentCard.value) return
  try {
    await http.post(`/study/review/${currentCard.value.id}`, { rating })
    reviewMsg.value = ['已重置为今日复习', '1 天后复习', '1 天后复习', '1 天后复习'][rating]
    // 移除当前卡片，前进
    reviewList.value.splice(reviewIndex.value, 1)
    if (reviewIndex.value >= reviewList.value.length) {
      reviewIndex.value = reviewList.value.length
    }
    showAnswer.value = false
  } catch (e: any) {
    reviewMsg.value = '提交失败：' + (e?.response?.data?.detail || '')
  }
}

function skipCard() {
  reviewIndex.value = Math.min(reviewIndex.value + 1, reviewList.value.length)
  showAnswer.value = false
  reviewMsg.value = ''
}

function startReview() {
  tab.value = 'review'
  loadQueue()
}

// ===== 方歌库 =====
const songs = ref<FormulaSong[]>([])
const songSearch = ref('')
const songSearchTimer = ref<ReturnType<typeof setTimeout> | null>(null)
const songModalOpen = ref(false)
const songEditing = ref<FormulaSong | null>(null)
const songForm = ref<FormulaSongIn>({ name: '', song: '', related_formula: '', notes: '', is_mastered: false })
const songSaving = ref(false)

const masteredCount = computed(() => songs.value.filter((s) => s.is_mastered).length)

// 批量导入
const batchModalOpen = ref(false)
const batchText = ref('')
const batchImporting = ref(false)
const batchResult = ref<{ imported: number; skipped: number; errors: string[] } | null>(null)

function openBatchModal() {
  batchText.value = ''
  batchResult.value = null
  batchModalOpen.value = true
}
function closeBatchModal() {
  batchModalOpen.value = false
}
async function submitBatch() {
  if (!batchText.value.trim()) return
  batchImporting.value = true
  batchResult.value = null
  try {
    const r = await FormulaSongAPI.batchImport(batchText.value)
    batchResult.value = r
    if (r.imported > 0) await loadSongs()
  } catch (e: any) {
    alert(`批量导入失败：${e?.response?.data?.detail || e?.message || ''}`)
  } finally {
    batchImporting.value = false
  }
}

async function loadSongs() {
  try {
    const params: { q?: string } = {}
    if (songSearch.value.trim()) params.q = songSearch.value.trim()
    songs.value = await FormulaSongAPI.list(params)
  } catch {
    songs.value = []
  }
}

function onSongSearchInput() {
  if (songSearchTimer.value) clearTimeout(songSearchTimer.value)
  songSearchTimer.value = setTimeout(() => loadSongs(), 300)
}

function openSongModal(song?: FormulaSong) {
  if (song) {
    songEditing.value = song
    songForm.value = {
      name: song.name,
      song: song.song,
      related_formula: song.related_formula || '',
      notes: song.notes || '',
      is_mastered: song.is_mastered,
    }
  } else {
    songEditing.value = null
    songForm.value = { name: '', song: '', related_formula: '', notes: '', is_mastered: false }
  }
  songModalOpen.value = true
}

function closeSongModal() {
  songModalOpen.value = false
  songEditing.value = null
}

async function saveSong() {
  if (!songForm.value.name.trim() || !songForm.value.song.trim()) return
  songSaving.value = true
  try {
    if (songEditing.value) {
      await FormulaSongAPI.update(songEditing.value.id, songForm.value)
    } else {
      await FormulaSongAPI.create(songForm.value)
    }
    closeSongModal()
    await loadSongs()
  } catch (e: any) {
    const detail = e?.response?.data?.detail || e?.message || ''
    alert(`保存失败：${detail}`)
  } finally {
    songSaving.value = false
  }
}

async function deleteSong(song: FormulaSong) {
  if (!confirm(`确定删除方歌「${song.name}」？`)) return
  await FormulaSongAPI.remove(song.id)
  await loadSongs()
}

async function toggleSong(song: FormulaSong) {
  await FormulaSongAPI.toggleTodo(song.id)
  await loadSongs()
}

onMounted(async () => {
  await loadLibraries()
  const baseId = route.query.base_id
  const tabQuery = route.query.tab as string | undefined
  if (tabQuery === 'songs') {
    // 搜索跳转：方歌库
    tab.value = 'songs'
    await loadSongs()
    if (route.query.focus) focusSongId.value = Number(route.query.focus)
  } else if (baseId) {
    tab.value = 'browse'
    loadCards(Number(baseId))
    focusCardId.value = route.query.focus ? Number(route.query.focus) : null
  }
})

// 高亮方歌（搜索跳转后）
const focusSongId = ref<number | null>(null)
function onSongRender(el: HTMLElement, id: number) {
  if (focusSongId.value && id === focusSongId.value) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.add('highlight')
    setTimeout(() => el.classList.remove('highlight'), 2500)
    focusSongId.value = null
  }
}

// 切换到方歌库 tab 时加载
watch(tab, (v) => {
  if (v === 'songs' && songs.value.length === 0) loadSongs()
})

function onCardRender(el: HTMLElement, id: number) {
  if (focusCardId.value && id === focusCardId.value) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.add('highlight')
    setTimeout(() => el.classList.remove('highlight'), 2500)
    focusCardId.value = null
  }
}
</script>

<template>
  <AppLayout>
    <div class="study">
      <!-- 模式切换 -->
      <div class="mode-tabs">
        <button class="mode-tab" :class="{ active: tab === 'browse' }" @click="tab = 'browse'">
          📚 浏览知识库
        </button>
        <button class="mode-tab" :class="{ active: tab === 'review' }" @click="startReview">
          🎯 今日复习
          <span v-if="queue.due.length + queue.new.length > 0" class="badge">
            {{ queue.due.length + queue.new.length }}
          </span>
        </button>
        <button class="mode-tab" :class="{ active: tab === 'songs' }" @click="tab = 'songs'">
          🎵 方歌库
          <span v-if="masteredCount > 0" class="badge badge-green">{{ masteredCount }}</span>
        </button>
      </div>

      <!-- 浏览模式 -->
      <template v-if="tab === 'browse'">
        <div class="lib-tabs">
          <button
            v-for="lib in libraries"
            :key="lib.id"
            class="lib-tab"
            :class="{ active: activeLib === lib.id }"
            @click="loadCards(lib.id)"
          >
            {{ lib.name }}
          </button>
        </div>

        <div v-if="activeLib === null" class="empty-hint">
          <p>选择上方知识库查看卡片</p>
        </div>

        <div v-else class="cards">
          <div v-if="cards.length === 0" class="empty-hint">
            <p>该知识库暂无卡片</p>
          </div>
          <div
            v-for="card in cards"
            :key="card.id"
            class="card-item"
            :ref="(el) => el && onCardRender(el as HTMLElement, card.id)"
          >
            <div class="card-name">{{ card.name }}</div>
            <div class="card-fields">
              <div v-for="(val, key) in card.fields" :key="key" class="field">
                <span class="field-key">{{ key }}</span>
                <span class="field-val">{{ val }}</span>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- 复习模式 -->
      <template v-else-if="tab === 'review'">
        <div v-if="reviewList.length === 0" class="empty-hint">
          <p>🎉 今日复习已完成！</p>
          <p class="sub">所有卡片都已复习，明天再来吧</p>
          <button class="refresh-btn" @click="loadQueue">刷新队列</button>
        </div>

        <div v-else class="review-area">
          <div class="review-progress">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: reviewProgress + '%' }"></div>
            </div>
            <span class="progress-text">{{ reviewIndex + 1 }} / {{ reviewTotal }}</span>
            <span class="review-timer">⏱ {{ reviewTimeText }}</span>
          </div>

          <div class="review-card" v-if="currentCard">
            <div class="review-card-header">
              <span class="card-type" :class="{ new: !currentCard.ease_factor }">
                {{ currentCard.ease_factor ? '复习' : '新卡' }}
              </span>
              <span class="card-name">{{ currentCard.name }}</span>
            </div>

            <!-- 正面：只显示名称/方名 -->
            <div v-if="!showAnswer" class="card-front">
              <div class="front-title">{{ currentCard.name }}</div>
              <button class="show-answer-btn" @click="showAnswer = true">显示答案</button>
            </div>

            <!-- 背面：显示所有字段 -->
            <div v-else class="card-back">
              <div class="card-fields">
                <div v-for="(val, key) in currentCard.fields" :key="key" class="field">
                  <span class="field-key">{{ key }}</span>
                  <span class="field-val">{{ val }}</span>
                </div>
              </div>
            </div>

            <!-- 评分按钮 -->
            <div v-if="showAnswer" class="rating-buttons">
              <button class="rate-btn rate-0" @click="submitReview(0)">
                <span class="rate-label">重来</span>
                <span class="rate-interval">今天</span>
              </button>
              <button class="rate-btn rate-1" @click="submitReview(1)">
                <span class="rate-label">困难</span>
                <span class="rate-interval">1天</span>
              </button>
              <button class="rate-btn rate-2" @click="submitReview(2)">
                <span class="rate-label">良好</span>
                <span class="rate-interval">~2.5天</span>
              </button>
              <button class="rate-btn rate-3" @click="submitReview(3)">
                <span class="rate-label">简单</span>
                <span class="rate-interval">~3天</span>
              </button>
            </div>

            <div v-if="reviewMsg" class="review-msg">{{ reviewMsg }}</div>
          </div>

          <button class="skip-btn" @click="skipCard">跳过 →</button>
        </div>
      </template>

      <!-- 方歌库模式 -->
      <template v-else-if="tab === 'songs'">
        <div class="songs-toolbar">
          <input
            v-model="songSearch"
            class="song-search"
            type="text"
            placeholder="搜索方剂名 / 方歌"
            @input="onSongSearchInput"
          />
          <button class="add-song-btn" @click="openSongModal()">+ 新增方歌</button>
          <button class="add-song-btn" @click="openBatchModal">📥 批量导入</button>
        </div>

        <div v-if="songs.length === 0" class="empty-hint">
          <p>🎶 暂无方歌</p>
          <p class="sub">点击右上角"新增方歌"开始背诵</p>
        </div>

        <div v-else class="songs-grid">
          <div
            v-for="song in songs"
            :key="song.id"
            class="song-card"
            :class="{ mastered: song.is_mastered }"
            :ref="(el) => { if (el) onSongRender(el as HTMLElement, song.id) }"
          >
            <div class="song-card-header">
              <span class="song-name">{{ song.name }}</span>
              <button
                class="mastered-toggle"
                :class="{ on: song.is_mastered }"
                :title="song.is_mastered ? '已加入待办，点击取消' : '加入待办'"
                @click="toggleSong(song)"
              >{{ song.is_mastered ? '✅' : '⬜' }}</button>
            </div>
            <div class="song-text">{{ song.song }}</div>
            <div v-if="song.related_formula" class="song-meta">
              <span class="meta-key">关联：</span>
              <span class="meta-val">{{ song.related_formula }}</span>
            </div>
            <div v-if="song.notes" class="song-notes">{{ song.notes }}</div>
            <div class="song-actions">
              <button class="song-edit-btn" @click="openSongModal(song)">编辑</button>
              <button class="song-del-btn" @click="deleteSong(song)">删除</button>
            </div>
          </div>
        </div>
      </template>

      <!-- 方歌新增/编辑弹窗 -->
      <div v-if="songModalOpen" class="song-modal-overlay" @click.self="closeSongModal">
        <div class="song-modal">
          <div class="song-modal-title">
            {{ songEditing ? '编辑方歌' : '新增方歌' }}
            <button class="song-modal-close" @click="closeSongModal">×</button>
          </div>
          <div class="song-modal-body">
            <label class="song-field">
              <span>方剂名 *</span>
              <input v-model="songForm.name" type="text" placeholder="如：麻黄汤" maxlength="100" />
            </label>
            <label class="song-field">
              <span>方歌 *</span>
              <textarea v-model="songForm.song" rows="4" placeholder="如：麻黄汤中臣桂枝，杏仁甘草四般施"></textarea>
            </label>
            <label class="song-field">
              <span>关联方剂</span>
              <input v-model="songForm.related_formula" type="text" placeholder="可选，文本即可" maxlength="100" />
            </label>
            <label class="song-field">
              <span>备注</span>
              <textarea v-model="songForm.notes" rows="2" placeholder="可选"></textarea>
            </label>
          </div>
          <div class="song-modal-footer">
            <button class="song-cancel-btn" @click="closeSongModal">取消</button>
            <button
              class="song-save-btn"
              :disabled="!songForm.name.trim() || !songForm.song.trim() || songSaving"
              @click="saveSong"
            >{{ songSaving ? '保存中…' : '保存' }}</button>
          </div>
        </div>
      </div>

      <!-- 批量导入弹窗 -->
      <div v-if="batchModalOpen" class="song-modal-overlay" @click.self="closeBatchModal">
        <div class="song-modal">
          <div class="song-modal-title">
            📥 批量导入方歌
            <button class="song-modal-close" @click="closeBatchModal">×</button>
          </div>
          <div class="song-modal-body">
            <p class="hint">三行一组（方剂名 / 方歌行1 / 方歌行2），组间空行分隔：</p>
            <textarea
              v-model="batchText"
              class="batch-textarea"
              placeholder="大青龙汤&#10;大青龙汤桂麻黄，杏草石膏姜枣藏。&#10;太阳无汗兼烦躁，散寒清热此方良。&#10;&#10;清燥救肺汤&#10;清燥救肺参草杷，石膏胶杏麦胡麻。&#10;经霜收下冬桑叶，清燥润肺效堪夸。"
              rows="14"
            ></textarea>
            <div v-if="batchResult" class="batch-result">
              ✅ 导入 {{ batchResult.imported }} 条，跳过 {{ batchResult.skipped }} 条
              <div v-if="batchResult.errors.length" class="batch-errors">
                <div v-for="(e, i) in batchResult.errors" :key="i">{{ e }}</div>
              </div>
            </div>
          </div>
          <div class="song-modal-footer">
            <button class="song-cancel-btn" @click="closeBatchModal">关闭</button>
            <button
              class="song-save-btn"
              :disabled="!batchText.trim() || batchImporting"
              @click="submitBatch"
            >{{ batchImporting ? '导入中…' : '开始导入' }}</button>
          </div>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<style scoped>
.study { display: flex; flex-direction: column; gap: 16px; }
.mode-tabs { display: flex; gap: 8px; }
.mode-tab {
  padding: 10px 18px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
}
.mode-tab.active {
  background: var(--color-primary);
  color: #fff;
  border-color: var(--color-primary);
}
.badge {
  background: #ef4444;
  color: #fff;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 10px;
}
.lib-tabs { display: flex; gap: 8px; flex-wrap: wrap; }
.lib-tab {
  padding: 8px 16px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
}
.lib-tab.active {
  background: var(--color-primary);
  color: #fff;
  border-color: var(--color-primary);
}
.empty-hint {
  padding: 60px 20px;
  text-align: center;
  color: var(--text-secondary);
}
.empty-hint .sub { font-size: 12px; margin-top: 8px; opacity: 0.7; }
.refresh-btn {
  margin-top: 16px;
  padding: 8px 20px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--color-primary);
  color: #fff;
  cursor: pointer;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}
.card-item {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  transition: all 0.2s;
}
.card-item.highlight {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary);
}
.card-name { font-size: 16px; font-weight: 600; margin-bottom: 10px; color: var(--text-primary); }
.card-fields { display: flex; flex-direction: column; gap: 6px; }
.field { display: flex; gap: 8px; font-size: 13px; }
.field-key { color: var(--text-secondary); min-width: 60px; flex-shrink: 0; }
.field-val { color: var(--text-primary); }

/* 复习模式 */
.review-area { display: flex; flex-direction: column; align-items: center; gap: 16px; }
.review-progress {
  display: flex; align-items: center; gap: 12px; width: 100%; max-width: 500px;
}
.progress-bar {
  flex: 1; height: 8px;
  background: var(--border-color);
  border-radius: 4px; overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.3s;
}
.progress-text { font-size: 13px; color: var(--text-secondary); white-space: nowrap; }
.review-timer {
  font-size: 13px; color: var(--text-secondary); white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.review-card {
  width: 100%; max-width: 560px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 24px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.06);
}
.review-card-header {
  display: flex; align-items: center; gap: 10px; margin-bottom: 16px;
}
.card-type {
  font-size: 11px; padding: 2px 8px;
  border-radius: 4px;
  background: var(--color-primary);
  color: #fff;
}
.card-type.new { background: #f59e0b; }
.review-card-header .card-name { margin-bottom: 0; }

.card-front {
  text-align: center; padding: 40px 20px;
}
.front-title { font-size: 28px; font-weight: 700; margin-bottom: 24px; }
.show-answer-btn {
  padding: 10px 28px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--color-primary);
  color: #fff;
  font-size: 15px;
  cursor: pointer;
}

.card-back {
  padding: 8px 0;
  border-top: 1px solid var(--border-color);
  padding-top: 16px;
}

.rating-buttons {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;
  margin-top: 20px;
}
.rate-btn {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 12px 8px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  cursor: pointer;
  transition: all 0.15s;
}
.rate-btn:hover { transform: translateY(-2px); }
.rate-label { font-size: 14px; font-weight: 600; }
.rate-interval { font-size: 11px; color: var(--text-secondary); }
.rate-0 { color: #ef4444; }
.rate-0:hover { background: #ef4444; color: #fff; border-color: #ef4444; }
.rate-1 { color: #f59e0b; }
.rate-1:hover { background: #f59e0b; color: #fff; border-color: #f59e0b; }
.rate-2 { color: #3b82f6; }
.rate-2:hover { background: #3b82f6; color: #fff; border-color: #3b82f6; }
.rate-3 { color: #10b981; }
.rate-3:hover { background: #10b981; color: #fff; border-color: #10b981; }

.review-msg {
  text-align: center; margin-top: 12px;
  font-size: 13px; color: var(--color-primary);
}
.skip-btn {
  padding: 8px 20px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}

/* 方歌库 */
.badge-green {
  background: #10b981;
}
.songs-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.song-search {
  flex: 1;
  min-width: 200px;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 14px;
}
.add-song-btn {
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--color-primary);
  color: #fff;
  font-size: 14px;
  cursor: pointer;
}
.add-song-btn:hover { opacity: 0.9; }
.songs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}
.song-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: all 0.2s;
}
.song-card.mastered {
  border-color: #10b981;
  background: color-mix(in srgb, #10b981 8%, var(--bg-card));
}
.song-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.song-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}
.mastered-toggle {
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  padding: 0;
}
.song-text {
  font-size: 14px;
  color: var(--text-primary);
  white-space: pre-wrap;
  line-height: 1.6;
}
.song-meta {
  font-size: 12px;
  display: flex;
  gap: 4px;
}
.meta-key { color: var(--text-secondary); }
.meta-val { color: var(--text-primary); }
.song-notes {
  font-size: 12px;
  color: var(--text-secondary);
  border-top: 1px dashed var(--border-color);
  padding-top: 6px;
  white-space: pre-wrap;
}
.song-actions {
  display: flex;
  gap: 8px;
  margin-top: auto;
  padding-top: 4px;
}
.song-edit-btn, .song-del-btn {
  padding: 4px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: transparent;
  font-size: 12px;
  cursor: pointer;
  color: var(--text-secondary);
}
.song-edit-btn:hover { color: var(--color-primary); border-color: var(--color-primary); }
.song-del-btn:hover { color: #ef4444; border-color: #ef4444; }

/* 方歌弹窗 */
.song-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}
.song-modal {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 480px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}
.song-modal-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border-color);
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}
.song-modal-close {
  border: none;
  background: transparent;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
  color: var(--text-secondary);
  padding: 0;
}
.song-modal-body {
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
}
.batch-textarea {
  width: 100%;
  min-height: 280px;
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-main);
  color: var(--text-primary);
  font-family: 'Cascadia Code', Consolas, monospace;
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
}
.batch-result {
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, #10b981 10%, var(--bg-card));
  color: #059669;
  font-size: 13px;
}
.batch-errors {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 12px;
}
.batch-errors div { padding: 2px 0; }
.song-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--text-secondary);
}
.song-field span { font-weight: 500; }
.song-field input[type="text"],
.song-field textarea {
  padding: 8px 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-main);
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
}
.song-field input:focus,
.song-field textarea:focus {
  outline: none;
  border-color: var(--color-primary);
}
.song-check {
  flex-direction: row;
  align-items: center;
  gap: 8px;
}
.song-check input { width: 16px; height: 16px; cursor: pointer; }
.song-modal-footer {
  padding: 12px 18px;
  border-top: 1px solid var(--border-color);
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
.song-cancel-btn {
  padding: 8px 16px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.song-save-btn {
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--color-primary);
  color: #fff;
  cursor: pointer;
}
.song-save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
