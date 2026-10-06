<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { http } from '@/api/http'
import { SearchAPI, type SearchItem } from '@/api/search'
import { useThemeStore } from '@/stores/theme'
import { useAuthStore } from '@/stores/auth'
import AppLayout from '@/components/AppLayout.vue'

const theme = useThemeStore()
const auth = useAuthStore()
const router = useRouter()

const stats = ref({
  today_review: 0,
  today_wrong: 0,
  today_todo: 0,
  study_duration: 0,
  streak_days: 0,
  weekly_completion_rate: 0
})
const heatmap = ref<{ date: string; duration: number; new_cards: number; review_cards: number; new_wrong: number }[]>([])
const charts = ref({
  weekly_duration_trend: [] as { date: string; duration: number }[],
  subject_wrong_distribution: [] as { name: string; value: number }[],
  review_completion_trend: [] as { date: string; review_cards: number; new_cards: number }[],
  knowledge_mastery_radar: {} as Record<string, number>,
})
const searchQuery = ref('')
const searchResults = ref<Record<string, SearchItem[]>>({})
const searchLoading = ref(false)
const showDropdown = ref(false)
let searchTimer: number | null = null

const totalResults = computed(() =>
  Object.values(searchResults.value).reduce((s, a) => s + (a?.length || 0), 0)
)

onMounted(async () => {
  try {
    const [s, h, c] = await Promise.all([
      http.get('/dashboard/stats'),
      http.get('/dashboard/heatmap'),
      http.get('/dashboard/charts')
    ])
    stats.value = s.data
    heatmap.value = h.data.data
    charts.value = c.data
  } catch (e) {
    // 容错
  }
})

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  const q = searchQuery.value.trim()
  if (!q) {
    searchResults.value = {}
    showDropdown.value = false
    return
  }
  showDropdown.value = true
  searchLoading.value = true
  searchTimer = window.setTimeout(async () => {
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

function gotoItem(item: SearchItem) {
  showDropdown.value = false
  searchQuery.value = ''
  searchResults.value = {}
  router.push({ name: 'study', query: { base_id: item.base_id, focus: item.id } })
}

function onSearchEnter() {
  if (!searchQuery.value.trim()) return
  // 回车跳转第一个结果
  const first = Object.values(searchResults.value).find((a) => a?.length)?.[0]
  if (first) gotoItem(first)
}

// 热力图：5 级颜色，按 duration 秒数分级
function heatLevel(duration: number): number {
  if (duration <= 0) return 0
  if (duration < 300) return 1        // < 5 分钟
  if (duration < 1800) return 2       // 5-30 分钟
  if (duration < 3600) return 3       // 30-60 分钟
  return 4                            // >= 1 小时
}

// 格式化时长
function fmtDuration(sec: number): string {
  if (sec <= 0) return '0 分钟'
  const m = Math.round(sec / 60)
  if (m < 60) return `${m} 分钟`
  return `${Math.floor(m / 60)} 时 ${m % 60} 分`
}

// ===== 饼图：错题分布 =====
const pieColors = ['#4A90E2', '#FF6B6B', '#51CF66', '#FFB740', '#A56FF5', '#26C9DD', '#F56FB3', '#7BC96F']
const pieSlices = computed(() => {
  const data = charts.value.subject_wrong_distribution
  const total = data.reduce((s, d) => s + d.value, 0)
  if (total === 0) return []
  let acc = 0
  const cx = 80, cy = 80, r = 60
  return data.map((d, i) => {
    const startAngle = (acc / total) * 2 * Math.PI - Math.PI / 2
    acc += d.value
    const endAngle = (acc / total) * 2 * Math.PI - Math.PI / 2
    const x1 = cx + r * Math.cos(startAngle)
    const y1 = cy + r * Math.sin(startAngle)
    const x2 = cx + r * Math.cos(endAngle)
    const y2 = cy + r * Math.sin(endAngle)
    const large = endAngle - startAngle > Math.PI ? 1 : 0
    const path = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`
    return { ...d, path, color: pieColors[i % pieColors.length], pct: ((d.value / total) * 100).toFixed(0) }
  })
})

// ===== 折线图：复习趋势 =====
const reviewLinePath = computed(() => {
  const data = charts.value.review_completion_trend
  if (data.length === 0) return { path: '', area: '', max: 0, pts: [] }
  const max = Math.max(1, ...data.map((d) => d.review_cards))
  const w = 280, h = 80, pad = 8
  const pts = data.map((d, i) => {
    const x = pad + (i / Math.max(1, data.length - 1)) * (w - pad * 2)
    const y = h - pad - (d.review_cards / max) * (h - pad * 2)
    return { x, y, label: d.date.slice(5), value: d.review_cards }
  })
  const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')
  const area = `${path} L ${pts[pts.length - 1].x} ${h - pad} L ${pts[0].x} ${h - pad} Z`
  return { path, area, max, pts }
})

// ===== 雷达图：知识库掌握度 =====
const radarPoints = computed(() => {
  const data = Object.entries(charts.value.knowledge_mastery_radar)
  if (data.length === 0) return { polygon: '', points: [] }
  const cx = 80, cy = 80, r = 60
  const n = data.length
  const angle = (i: number) => (i / n) * 2 * Math.PI - Math.PI / 2
  const points = data.map(([name, val], i) => {
    const a = angle(i)
    const x = cx + r * val * Math.cos(a)
    const y = cy + r * val * Math.sin(a)
    const lx = cx + (r + 18) * Math.cos(a)
    const ly = cy + (r + 18) * Math.sin(a)
    return { x, y, lx, ly, name, val: Math.round(val * 100) }
  })
  const polygon = points.map((p) => `${p.x} ${p.y}`).join(' ')
  return { polygon, points }
})
</script>

<template>
  <AppLayout>
    <div class="home">
      <!-- 顶部快速搜索 -->
      <section class="search-bar card">
        <span class="search-icon">🔍</span>
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索方剂 / 中药 / 穴位（按回车跳转）"
          @input="onSearchInput"
          @focus="searchQuery.trim() && (showDropdown = true)"
          @keyup.enter="onSearchEnter"
          @keydown.esc="showDropdown = false"
        />
        <div v-if="searchLoading" class="search-hint">搜索中…</div>

        <!-- 搜索结果下拉 -->
        <div v-if="showDropdown" class="search-dropdown">
          <div v-if="totalResults === 0 && !searchLoading" class="search-empty">
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
      </section>

      <!-- 仪表盘卡片 -->
      <section class="stats-grid">
        <div
          class="stat card"
          v-for="card in [
            { label: '今日复习', value: stats.today_review, color: 'var(--color-primary)' },
            { label: '今日错题', value: stats.today_wrong, color: 'var(--color-accent)' },
            { label: '今日待办', value: stats.today_todo, color: 'var(--color-success)' },
            { label: '学习时长', value: fmtDuration(stats.study_duration), color: '#FFB740' },
            { label: '连续打卡', value: stats.streak_days + '天', color: '#A56FF5' },
            { label: '本周完成率', value: (stats.weekly_completion_rate * 100).toFixed(0) + '%', color: '#26C9DD' }
          ]"
          :key="card.label"
        >
          <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
          <div class="stat-label">{{ card.label }}</div>
        </div>
      </section>

      <!-- 学习热力图 -->
      <section class="card">
        <div class="heatmap-header">
          <h3 class="section-title">学习热力图</h3>
          <div class="heatmap-legend">
            <span>少</span>
            <span v-for="l in 5" :key="l" class="legend-cell" :class="`lv${l}`"></span>
            <span>多</span>
          </div>
        </div>
        <div class="heatmap">
          <div
            v-for="day in heatmap"
            :key="day.date"
            class="heat-cell"
            :class="`lv${heatLevel(day.duration)}`"
            :title="`${day.date}｜学习 ${fmtDuration(day.duration)}｜新卡 ${day.new_cards}｜复习 ${day.review_cards}｜错题 ${day.new_wrong}`"
          ></div>
        </div>
      </section>

      <!-- 数据图表 -->
      <section class="charts-grid">
        <!-- 错题分布饼图 -->
        <div class="card chart-card">
          <h3 class="section-title">错题分布</h3>
          <div v-if="pieSlices.length === 0" class="chart-empty">暂无错题数据</div>
          <div v-else class="pie-wrap">
            <svg viewBox="0 0 160 160" class="pie-svg">
              <path v-for="s in pieSlices" :key="s.name" :d="s.path" :fill="s.color" :title="`${s.name}: ${s.value} (${s.pct}%)`" />
            </svg>
            <div class="pie-legend">
              <div v-for="s in pieSlices" :key="s.name" class="legend-row">
                <span class="legend-dot" :style="{ background: s.color }"></span>
                <span class="legend-name">{{ s.name }}</span>
                <span class="legend-val">{{ s.value }} ({{ s.pct }}%)</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 复习趋势折线图 -->
        <div class="card chart-card">
          <h3 class="section-title">近 7 天复习趋势</h3>
          <div v-if="reviewLinePath.pts.length === 0" class="chart-empty">暂无数据</div>
          <svg v-else viewBox="0 0 296 96" class="line-svg">
            <path :d="reviewLinePath.area" fill="rgba(74,144,226,0.15)" />
            <path :d="reviewLinePath.path" fill="none" stroke="#4A90E2" stroke-width="2" />
            <circle v-for="p in reviewLinePath.pts" :key="p.label" :cx="p.x" :cy="p.y" r="3" fill="#4A90E2">
              <title>{{ p.label }}: {{ p.value }} 张</title>
            </circle>
            <text v-for="p in reviewLinePath.pts" :key="'t'+p.label" :x="p.x" y="92" font-size="9" text-anchor="middle" fill="var(--text-secondary)">{{ p.label }}</text>
          </svg>
        </div>

        <!-- 知识库掌握度雷达图 -->
        <div class="card chart-card">
          <h3 class="section-title">知识库掌握度</h3>
          <div v-if="radarPoints.points.length === 0" class="chart-empty">暂无知识库</div>
          <svg v-else viewBox="0 0 160 160" class="radar-svg">
            <!-- 背景网格 -->
            <polygon v-for="ring in [1,2,3,4]" :key="ring"
              :points="radarPoints.points.map((_, i) => { const a = (i / radarPoints.points.length) * 2 * Math.PI - Math.PI / 2; return `${80 + 60 * (ring/4) * Math.cos(a)} ${80 + 60 * (ring/4) * Math.sin(a)}` }).join(' ')"
              fill="none" stroke="var(--border-color)" stroke-width="0.5" />
            <line v-for="(p, i) in radarPoints.points" :key="'a'+i" x1="80" y1="80" :x2="80 + 60 * Math.cos((i / radarPoints.points.length) * 2 * Math.PI - Math.PI / 2)" :y2="80 + 60 * Math.sin((i / radarPoints.points.length) * 2 * Math.PI - Math.PI / 2)" stroke="var(--border-color)" stroke-width="0.5" />
            <!-- 数据多边形 -->
            <polygon :points="radarPoints.polygon" fill="rgba(81,207,102,0.3)" stroke="#51CF66" stroke-width="2" />
            <circle v-for="p in radarPoints.points" :key="'p'+p.name" :cx="p.x" :cy="p.y" r="3" fill="#51CF66" />
            <text v-for="p in radarPoints.points" :key="'l'+p.name" :x="p.lx" :y="p.ly" font-size="10" text-anchor="middle" dominant-baseline="middle" fill="var(--text-secondary)">{{ p.name }} {{ p.val }}%</text>
          </svg>
        </div>
      </section>

      <!-- 快捷入口 -->
      <section class="quick-actions">
        <router-link to="/study" class="quick card">📚 今日复习</router-link>
        <router-link to="/wrong-questions" class="quick card">📝 快录错题</router-link>
        <router-link to="/todos" class="quick card">✓ 新建待办</router-link>
        <router-link to="/plans" class="quick card">📅 今日计划</router-link>
      </section>
    </div>
  </AppLayout>
</template>

<style scoped>
.home { display: flex; flex-direction: column; gap: 18px; }

/* 搜索框 */
.search-bar {
  position: relative;
  display: flex; align-items: center; gap: 10px;
  padding: 12px 16px;
}
.search-icon { font-size: 18px; opacity: 0.6; }
.search-bar input {
  flex: 1; border: none; background: transparent;
  font-size: 15px; padding: 4px 0;
}
.search-bar input:focus { outline: none; }
.search-hint { font-size: 12px; color: var(--text-secondary); }
.search-dropdown {
  position: absolute;
  top: 100%; left: 0; right: 0;
  margin-top: 4px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  max-height: 50vh; overflow-y: auto;
  z-index: 50;
}
.search-empty { padding: 20px; text-align: center; color: var(--text-secondary); font-size: 13px; }
.search-group { padding: 4px 8px; }
.search-group-title {
  font-size: 12px; color: var(--text-secondary);
  padding: 8px 10px 4px; font-weight: 600;
}
.search-item {
  padding: 8px 10px; border-radius: var(--radius-sm); cursor: pointer;
}
.search-item:hover { background: var(--bg-main); }
.search-name { font-size: 14px; font-weight: 500; }
.search-meta {
  font-size: 12px; color: var(--text-secondary); margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* 统计卡片 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}
.stat { display: flex; flex-direction: column; gap: 4px; text-align: center; }
.stat-value { font-size: 28px; font-weight: 700; }
.stat-label { color: var(--text-secondary); font-size: 13px; }

/* 热力图 */
.section-title { font-size: 16px; margin: 0; }
.heatmap-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px;
}
.heatmap-legend { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--text-secondary); }
.legend-cell { width: 12px; height: 12px; border-radius: 2px; }
.heatmap {
  display: grid;
  grid-template-columns: repeat(53, 1fr);
  grid-auto-rows: 12px;
  gap: 3px;
}
.heat-cell { border-radius: 2px; background: var(--border-color); }
.heat-cell.lv1 { background: #c6e48b; opacity: 0.85; }
.heat-cell.lv2 { background: #7bc96f; }
.heat-cell.lv3 { background: #239a3b; }
.heat-cell.lv4 { background: #196127; }
.dark .heat-cell.lv1 { background: #0e4429; }
.dark .heat-cell.lv2 { background: #006d32; }
.dark .heat-cell.lv3 { background: #26a641; }
.dark .heat-cell.lv4 { background: #39d353; }

/* 快捷入口 */
.quick-actions {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}
.quick {
  text-align: center; font-weight: 600;
  color: var(--color-primary); padding: 16px;
}
.quick:hover { text-decoration: none; transform: translateY(-2px); }

/* 图表 */
.charts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}
.chart-card { padding: 16px; }
.chart-card .section-title { margin-bottom: 12px; }
.chart-empty {
  text-align: center; padding: 30px 10px;
  color: var(--text-secondary); font-size: 13px;
}
.pie-wrap { display: flex; align-items: center; gap: 12px; }
.pie-svg { width: 120px; height: 120px; flex-shrink: 0; }
.pie-legend { flex: 1; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.legend-row { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.legend-dot { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
.legend-name { color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.legend-val { color: var(--text-secondary); margin-left: auto; }
.line-svg { width: 100%; height: 96px; }
.radar-svg { width: 100%; max-width: 220px; height: auto; display: block; margin: 0 auto; }
</style>
