import { http } from './http'

export interface SetupStatus {
  initialized: boolean
}

export interface LoginResp {
  access_token: string
  refresh_token: string
  token_type: string
  user: { id: number; username: string; settings?: Record<string, any> }
}

export const AuthAPI = {
  setupStatus(): Promise<SetupStatus> {
    return http.get('/auth/setup/status').then((r) => r.data)
  },
  setup(username: string, password: string): Promise<LoginResp> {
    return http.post('/auth/setup', { username, password }).then((r) => r.data)
  },
  login(username: string, password: string): Promise<LoginResp> {
    return http.post('/auth/login', { username, password }).then((r) => r.data)
  },
  me(): Promise<{ id: number; username: string }> {
    return http.get('/auth/me').then((r) => r.data)
  }
}
