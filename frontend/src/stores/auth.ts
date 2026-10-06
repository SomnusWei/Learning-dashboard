import { defineStore } from 'pinia'
import { AuthAPI, type LoginResp } from '@/api/auth'
import { setTokens, clearTokens } from '@/api/http'

interface User {
  id: number
  username: string
  settings?: Record<string, any>
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as User | null,
    initialized: false
  }),
  getters: {
    isLoggedIn: (state) => !!state.user
  },
  actions: {
    async fetchSetupStatus() {
      const { initialized } = await AuthAPI.setupStatus()
      this.initialized = initialized
      return initialized
    },
    async setup(username: string, password: string) {
      const r: LoginResp = await AuthAPI.setup(username, password)
      this.applyTokens(r)
      return r
    },
    async login(username: string, password: string) {
      const r: LoginResp = await AuthAPI.login(username, password)
      this.applyTokens(r)
      return r
    },
    async fetchMe() {
      try {
        const u = await AuthAPI.me()
        this.user = u as User
        return u
      } catch {
        this.logout()
        return null
      }
    },
    applyTokens(r: LoginResp) {
      setTokens(r.access_token, r.refresh_token)
      this.user = r.user
    },
    logout() {
      clearTokens()
      this.user = null
    }
  }
})
