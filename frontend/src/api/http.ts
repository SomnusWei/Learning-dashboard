import axios, { AxiosError, type AxiosInstance } from 'axios'

const apiBase = (typeof __API_BASE__ !== 'undefined' ? __API_BASE__ : '') || ''
const tokenKey = 'ld_access_token'
const refreshKey = 'ld_refresh_token'

export const http: AxiosInstance = axios.create({
  baseURL: `${apiBase}/api/v1`,
  timeout: 15000,
  withCredentials: false
})

// 请求拦截：注入 Authorization
http.interceptors.request.use((config) => {
  const token = localStorage.getItem(tokenKey)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：401 自动刷新 token 一次
let refreshing: Promise<string | null> | null = null

http.interceptors.response.use(
  (res) => res,
  async (err: AxiosError) => {
    const original = err.config as any
    if (err.response?.status === 401 && !original.__retry) {
      original.__retry = true
      try {
        refreshing ??= refreshAccessToken()
        const newToken = await refreshing
        refreshing = null
        if (newToken) {
          localStorage.setItem(tokenKey, newToken)
          original.headers.Authorization = `Bearer ${newToken}`
          return http(original)
        }
      } catch (e) {
        // 刷新失败，跳登录
      }
      clearTokens()
      if (location.pathname !== '/login') {
        location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem(refreshKey)
  if (!refreshToken) return null
  const { data } = await axios.post(`${apiBase}/api/v1/auth/refresh`, { refresh_token: refreshToken })
  localStorage.setItem(tokenKey, data.access_token)
  localStorage.setItem(refreshKey, data.refresh_token)
  return data.access_token
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(tokenKey, access)
  localStorage.setItem(refreshKey, refresh)
}

export function clearTokens() {
  localStorage.removeItem(tokenKey)
  localStorage.removeItem(refreshKey)
}

export function getToken(): string | null {
  return localStorage.getItem(tokenKey)
}
