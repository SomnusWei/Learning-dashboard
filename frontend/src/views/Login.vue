<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'

const auth = useAuthStore()
const theme = useThemeStore()
const router = useRouter()

const form = ref({ username: '', password: '' })
const loading = ref(false)
const error = ref('')
const initialized = ref(true)

onMounted(async () => {
  try {
    initialized.value = await auth.fetchSetupStatus()
  } catch (e) {
    initialized.value = false
  }
})

async function onSubmit() {
  loading.value = true
  error.value = ''
  try {
    await auth.login(form.value.username, form.value.password)
    router.push('/')
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '登录失败，请检查用户名和密码'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrapper">
    <div class="login-card card">
      <div class="brand">
        <div class="logo">学</div>
        <h1>个人学习工作台</h1>
        <p class="subtitle">中医学习 · 错题 · 记忆 · 计划</p>
      </div>

      <form @submit.prevent="onSubmit" class="login-form">
        <div class="field">
          <label>用户名</label>
          <input v-model="form.username" type="text" placeholder="请输入用户名" required autocomplete="username" />
        </div>
        <div class="field">
          <label>密码</label>
          <input v-model="form.password" type="password" placeholder="请输入密码" required autocomplete="current-password" />
        </div>

        <p v-if="error" class="error">{{ error }}</p>

        <button class="btn-primary" type="submit" :disabled="loading">
          {{ loading ? '登录中...' : '登录' }}
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
.login-wrapper {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.login-card {
  width: 100%;
  max-width: 420px;
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
  box-shadow: var(--shadow-md);
}
h1 { font-size: 22px; margin-bottom: 6px; }
.subtitle { color: var(--text-secondary); font-size: 13px; }
.login-form { display: flex; flex-direction: column; gap: 14px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-size: 13px; color: var(--text-secondary); }
.btn-primary { width: 100%; padding: 12px; font-size: 15px; font-weight: 600; }
.error {
  color: var(--color-accent);
  font-size: 13px;
  text-align: center;
  margin: 4px 0;
}
.footer { margin-top: 20px; text-align: center; }
.btn-text {
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  padding: 6px 12px;
}
.btn-text:hover { color: var(--color-primary); }
</style>
