import { http } from './http'

export interface SearchItem {
  id: number
  base_id: number
  name: string
  fields: Record<string, any>
  images: any[]
}

export interface SearchResp {
  query: string
  results: Record<string, SearchItem[]>
}

export const SearchAPI = {
  search(q: string): Promise<SearchResp> {
    return http.get('/search', { params: { q } }).then((r) => r.data)
  },
  suggest(q: string): Promise<{ suggestions: string[] }> {
    return http.get('/search/suggest', { params: { q } }).then((r) => r.data)
  }
}
