const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type Problem = {
  contest_id: number
  problem_index: string
  name: string
  rating: number | null
  tags: string[]
  solved_at: string
  url: string
}

export type Day = { date: string; solved_count: number; problems: Problem[] }
export type CalendarDay = { date: string; solved_count: number; ratings: number[] }
export type Stats = {
  handle: string
  total_solved: number
  current_streak: number
  max_rating_solved: number | null
  calendar: CalendarDay[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, init)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail ?? 'Request failed')
  return data
}

export function syncUser(handle: string) {
  return request<{ handle: string; fetched: number; inserted: number; new_solved: number }>(`/api/users/${encodeURIComponent(handle)}/sync`, { method: 'POST' })
}

export function fetchStats(handle: string) {
  return request<Stats>(`/api/users/${encodeURIComponent(handle)}/stats`)
}

export function fetchDay(handle: string, day: string) {
  return request<Day>(`/api/users/${encodeURIComponent(handle)}/day/${day}`)
}
