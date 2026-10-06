<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'

const auth = useAuthStore()
const theme = useThemeStore()
const router = useRouter()

const form = ref({
  username: '',
  password: '',
  confirm: ''
})
const loading = ref(false)
const error = ref('')

onMounted(async () => {
  const initialized = await auth.fetchSetupStatus()
  if (initialized) {
    router.replace('/login')
  }
})

async function onSubmit() {
  if (form.value.password !== form.value.confirm) {
    error.value = '两次输入的密码不一致'
    return
  }
  if (form.value.password.length < 6) {
    error.value = '密码至少 6 位'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await auth.setup(form.value.username, form.value.password)
    router.push('/')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '初始化失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="setup-wrapper">
    <div class="setup-card card">
      <div class="brand">
        <div class="logo">学</div>
        <h1>首次启动初始化</h1>
        <p class="subtitle">设置管理员账号密码，初始化后系统将预置中医科目标签与中药/方剂/穴位三大知识库</p>
      </div>

      <form @submit.prevent="onSubmit" class="setup-form">
        <div class="field">
          <label>用户名（3-50 字母/数字/下划线）</label>
          <input v-model="form.username" type="text" required pattern="[a-zA-Z0-9_]{3,50}" autocomplete="username" />
        </div>
        <div class="field">
          <label>密码（至少 6 位）</label>
          <input v-model="form.password" type="password" required minlength="6" autocomplete="new-password" />
        </div>
        <div class="field">
          <label>确认密码</label>
          <input v-model="form.confirm" type="password" required minlength="6" autocomplete="new-password" />
        </div>

        <p v-if="error" class="error">{{ error }}</p>

        <button class="btn-primary" type="submit" :disabled="loading">
          {{ loading ? '初始化中...' : '完成初始化' }}
        </button>
      </form>

      <div class="footer">
        <button class="btn-text" @click="theme.toggle()">
          切换到{{ theme.mode === 'light' ? '黑夜' : '白天' }}模式
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.setup-wrapper {
  min-height: 100vh;
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.setup-card {
  width: 100%; max-width: 460px;
  padding: 36px 32px;
}
.brand { text-align: center; margin-bottom: 28px; }
.logo {
  width: 64px; height: 64px;
  margin: 0 auto 14px;
  border-radius: 18px;
  background: linear-gradient(135deg, var(--color-primary), var(--color-accent));
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 30px; font-weight: 700;
}
h1 { font-size: 22px; margin-bottom: 6px; }
.subtitle { color: var(--text-secondary); font-size: 13px; line-height: 1.5; }
.setup-form { display: flex; flex-direction: column; gap: 14px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-size: 13px; color: var(--text-secondary); }
.btn-primary { width: 100%; padding: 12px; font-size: 15px; font-weight: 600; }
.error { color: var(--color-accent); font-size: 13px; text-align: center; }
.footer { margin-top: 20px; text-align: center; }
.btn-text { background: transparent; color: var(--text-secondary); font-size: 13px; padding: 6px 12px; }
</style>
