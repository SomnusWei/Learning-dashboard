import { http } from './http'

export interface FormulaSong {
  id: number
  name: string
  song: string
  related_formula?: string | null
  notes?: string | null
  is_mastered: boolean
  created_at?: string | null
  updated_at?: string | null
}

export interface FormulaSongIn {
  name: string
  song: string
  related_formula?: string | null
  notes?: string | null
  is_mastered?: boolean
}

export const FormulaSongAPI = {
  list(params?: { q?: string; is_mastered?: boolean }): Promise<FormulaSong[]> {
    return http.get('/formula-songs', { params }).then((r) => r.data)
  },
  create(body: FormulaSongIn): Promise<FormulaSong> {
    return http.post('/formula-songs', body).then((r) => r.data)
  },
  update(id: number, body: FormulaSongIn): Promise<FormulaSong> {
    return http.put(`/formula-songs/${id}`, body).then((r) => r.data)
  },
  remove(id: number): Promise<void> {
    return http.delete(`/formula-songs/${id}`)
  },
  toggleTodo(id: number): Promise<FormulaSong> {
    return http.patch(`/formula-songs/${id}/toggle-todo`).then((r) => r.data)
  },
  batchImport(text: string): Promise<{ imported: number; skipped: number; errors: string[] }> {
    return http.post('/formula-songs/batch', { text }).then((r) => r.data)
  }
}
