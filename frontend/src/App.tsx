import { useEffect, useMemo, useState } from 'react'
import { fetchDay, fetchStats, syncUser, type Day, type Stats } from './api'

function localDateString(d = new Date()) {
  const y = d.getFullYear()
  const m = `${d.getMonth() + 1}`.padStart(2, '0')
  const day = `${d.getDate()}`.padStart(2, '0')
  return `${y}-${m}-${day}`
}

function App() {
  const [handle, setHandle] = useState('Neoeon')
  const [activeHandle, setActiveHandle] = useState('')
  const [stats, setStats] = useState<Stats | null>(null)
  const [selectedDate, setSelectedDate] = useState(localDateString())
  const [day, setDay] = useState<Day | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  async function refresh(target = activeHandle) {
    if (!target) return
    setLoading(true)
    try {
      const [s, d] = await Promise.all([fetchStats(target), fetchDay(target, selectedDate)])
      setStats(s); setDay(d); setMessage('')
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Could not load data')
    } finally { setLoading(false) }
  }

  async function connect() {
    setLoading(true); setMessage('Syncing Codeforces submissions…')
    try {
      const result = await syncUser(handle.trim())
      setActiveHandle(result.handle)
      const [s, d] = await Promise.all([fetchStats(result.handle), fetchDay(result.handle, selectedDate)])
      setStats(s); setDay(d)
      setMessage(`Synced ${result.inserted} new submissions; ${result.new_solved} were accepted.`)
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Sync failed')
    } finally { setLoading(false) }
  }

  useEffect(() => {
    if (!activeHandle) return
    fetchDay(activeHandle, selectedDate).then(setDay).catch(() => undefined)
  }, [selectedDate, activeHandle])

  const distribution = useMemo(() => {
    if (!stats) return []
    const counts = new Map<number, number>()
    for (const d of stats.calendar) for (const r of d.ratings) counts.set(r, (counts.get(r) ?? 0) + 1)
    return [...counts.entries()].sort((a, b) => a[0] - b[0])
  }, [stats])

  const cells = useMemo(() => {
    if (!stats) return []
    const map = new Map(stats.calendar.map(d => [d.date, d]))
    const end = new Date()
    const start = new Date(end); start.setDate(end.getDate() - 119)
    return Array.from({ length: 120 }, (_, i) => {
      const d = new Date(start); d.setDate(start.getDate() + i)
      const key = localDateString(d)
      return { key, count: map.get(key)?.solved_count ?? 0 }
    })
  }, [stats])

  return (
    <main className="page">
      <section className="hero">
        <div>
          <p className="eyebrow">CODEFORCES PRACTICE LOG</p>
          <h1>CF Tracker</h1>
          <p className="sub">Every solved problem. Its exact rating. Its exact day.</p>
        </div>
        <div className="connect">
          <input value={handle} onChange={e => setHandle(e.target.value)} placeholder="Codeforces handle" />
          <button onClick={connect} disabled={loading || !handle.trim()}>{loading ? 'Syncing…' : 'Sync handle'}</button>
        </div>
      </section>

      {message && <div className="notice">{message}</div>}

      {stats ? <>
        <section className="stats">
          <div><span>Total solved</span><strong>{stats.total_solved}</strong></div>
          <div><span>Current streak</span><strong>{stats.current_streak}d</strong></div>
          <div><span>Highest rating solved</span><strong>{stats.max_rating_solved ?? '—'}</strong></div>
        </section>

        <section className="panel">
          <div className="panel-head"><div><p className="eyebrow">ACTIVITY</p><h2>Practice calendar</h2></div><button className="ghost" onClick={() => refresh()}>{loading ? 'Refreshing…' : 'Refresh'}</button></div>
          <div className="heatmap">{cells.map(c => <button key={c.key} title={`${c.key}: ${c.count} solved`} className={`cell level-${Math.min(c.count, 5)}`} onClick={() => setSelectedDate(c.key)} />)}</div>
        </section>

        <section className="columns">
          <div className="panel">
            <div className="panel-head"><div><p className="eyebrow">SELECTED DAY</p><h2>{selectedDate}</h2></div><input type="date" value={selectedDate} onChange={e => setSelectedDate(e.target.value)} /></div>
            <div className="day-count">{day?.solved_count ?? 0} solved</div>
            <div className="problems">
              {day?.problems.map(p => <a className="problem" href={p.url} target="_blank" rel="noreferrer" key={`${p.contest_id}-${p.problem_index}`}>
                <span className="badge">{p.rating ?? '?'}</span>
                <div><b>{p.problem_index}. {p.name}</b><small>{p.tags.join(' · ') || 'No tags'}</small></div>
              </a>)}
              {day && day.problems.length === 0 && <div className="empty">No accepted solutions recorded for this day.</div>}
            </div>
          </div>

          <div className="panel">
            <p className="eyebrow">ALL TIME</p><h2>Rating breakdown</h2>
            <div className="bars">
              {distribution.map(([rating, count]) => <div className="bar-row" key={rating}><span>{rating}</span><div className="bar"><i style={{ width: `${Math.max(4, count / Math.max(...distribution.map(x => x[1])) * 100)}%` }} /></div><b>{count}</b></div>)}
            </div>
          </div>
        </section>
      </> : <section className="welcome"><h2>Connect your Codeforces handle</h2><p>Hit “Sync handle” to import your submissions and start building the history.</p></section>}
    </main>
  )
}

export default App
