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

export type Quest = {
  id: string
  title: string
  description: string
  progress: number
  target: number
  reward_xp: number
  completed: boolean
}

export type Challenge = {
  id: string
  slug: string
  title: string
  description: string
  icon: string
  reward_xp: number
  starts_on: string | null
  ends_on: string | null
  definition: Record<string, unknown>
  active: boolean
  progress: number
  target: number
  completed: boolean
}

export type AdminChallenge = Omit<Challenge, 'progress' | 'target' | 'completed'> & {
  created_at: string
}

export type Achievement = {
  id: string
  title: string
  description: string
  icon: string
  progress: number
  target: number
  unlocked: boolean
}

export type Profile = {
  handle: string
  title: string
  level: number
  score: number
  level_xp: number
  next_level_xp: number
  total_solved: number
  current_streak: number
  active_days: number
  max_rating_solved: number | null
  weekly_solved: number
}

export type Game = {
  profile: Profile
  daily_quests: Quest[]
  weekly_challenges: Quest[]
  custom_challenges: Challenge[]
  achievements: Achievement[]
  today: string
  weekly_start: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, init)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail ?? 'Request failed')
  return data
}

export function syncUser(handle: string) {
  return request<{ handle: string; fetched: number; inserted: number; new_solved: number }>(
    `/api/users/${encodeURIComponent(handle)}/sync`,
    { method: 'POST' },
  )
}

export function fetchGame(handle: string) {
  return request<Game>(`/api/users/${encodeURIComponent(handle)}/game`)
}

export function fetchStats(handle: string) {
  return request<Stats>(`/api/users/${encodeURIComponent(handle)}/stats`)
}

export function fetchDay(handle: string, day: string) {
  return request<Day>(`/api/users/${encodeURIComponent(handle)}/day/${day}`)
}

export function createAdminChallenge(adminKey: string, payload: unknown) {
  return request<AdminChallenge>('/api/admin/challenges', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Key': adminKey,
    },
    body: JSON.stringify(payload),
  })
}

export function fetchAdminChallenges(adminKey: string) {
  return request<AdminChallenge[]>('/api/admin/challenges', {
    headers: { 'X-Admin-Key': adminKey },
  })
}

export function archiveAdminChallenge(adminKey: string, id: string) {
  return request<{ ok: boolean }>(`/api/admin/challenges/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: { 'X-Admin-Key': adminKey },
  })
}
