import { useEffect, useMemo, useState } from 'react'
import {
  archiveAdminChallenge,
  createAdminChallenge,
  fetchAdminChallenges,
  fetchDay,
  fetchGame,
  syncUser,
  type AdminChallenge,
  type Challenge,
  type Day,
  type Game,
} from './api'

function localDateString(d = new Date()) {
  const y = d.getFullYear()
  const m = `${d.getMonth() + 1}`.padStart(2, '0')
  const day = `${d.getDate()}`.padStart(2, '0')
  return `${y}-${m}-${day}`
}

function progressPct(progress: number, target: number) {
  if (target <= 0) return 0
  return Math.min(100, Math.round((progress / target) * 100))
}

const challengeExample = JSON.stringify(
  {
    slug: 'dp-hunter',
    title: 'DP Hunter',
    description: 'Solve 5 dynamic programming problems rated 1200 or higher.',
    icon: '🧠',
    reward_xp: 250,
    starts_on: localDateString(),
    ends_on: localDateString(new Date(Date.now() + 6 * 86400000)),
    definition: {
      type: 'solve_count',
      target: 5,
      filters: {
        min_rating: 1200,
        tags_any: ['dp'],
      },
    },
    active: true,
  },
  null,
  2,
)

function App() {
  const [handle, setHandle] = useState('Neoeon')
  const [activeHandle, setActiveHandle] = useState('')
  const [game, setGame] = useState<Game | null>(null)
  const [day, setDay] = useState<Day | null>(null)
  const [selectedDate, setSelectedDate] = useState(localDateString())
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [message, setMessage] = useState('')
  const [tab, setTab] = useState<'home' | 'quests' | 'profile' | 'admin'>('home')
  const [adminKey, setAdminKey] = useState(() => sessionStorage.getItem('cfquest_admin_key') ?? '')
  const [adminAuthed, setAdminAuthed] = useState(false)
  const [adminChallenges, setAdminChallenges] = useState<AdminChallenge[]>([])
  const [challengeJson, setChallengeJson] = useState(challengeExample)
  const [adminLoading, setAdminLoading] = useState(false)

  async function load(target: string, date = selectedDate) {
    const [g, d] = await Promise.all([fetchGame(target), fetchDay(target, date)])
    setGame(g)
    setDay(d)
  }

  async function connect() {
    const target = handle.trim()
    if (!target) return
    setSyncing(true)
    setMessage('Syncing new submissions…')
    try {
      const result = await syncUser(target)
      setActiveHandle(result.handle)
      await load(result.handle)
      setMessage(result.inserted === 0 ? 'You are up to date. ⚡' : `+${result.new_solved} new solves synced.`)
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Sync failed')
    } finally {
      setSyncing(false)
    }
  }

  async function refresh() {
    if (!activeHandle) return
    setLoading(true)
    try {
      await load(activeHandle)
      setMessage('Tracker refreshed.')
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Could not refresh')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!activeHandle) return
    fetchDay(activeHandle, selectedDate).then(setDay).catch(() => undefined)
  }, [selectedDate, activeHandle])

  const profile = game?.profile
  const currentFloor = profile ? 250 * (profile.level - 1) * (profile.level - 1) : 0
  const levelPct = profile ? Math.round((profile.level_xp / Math.max(profile.next_level_xp - currentFloor, 1)) * 100) : 0
  const questDone = game?.daily_quests.filter(q => q.completed).length ?? 0
  const challengeDone = game?.weekly_challenges.filter(q => q.completed).length ?? 0

  async function openAdmin() {
    if (!adminKey.trim()) {
      setMessage('Enter your admin key first.')
      return
    }
    sessionStorage.setItem('cfquest_admin_key', adminKey.trim())
    setAdminLoading(true)
    try {
      const rows = await fetchAdminChallenges(adminKey.trim())
      setAdminChallenges(rows)
      setAdminAuthed(true)
      setTab('admin')
    } catch (e) {
      setAdminAuthed(false)
      setMessage(e instanceof Error ? e.message : 'Admin authentication failed')
    } finally {
      setAdminLoading(false)
    }
  }

  async function addChallenge() {
    if (!adminKey.trim()) return setMessage('Enter your admin key.')
    setAdminLoading(true)
    try {
      const payload = JSON.parse(challengeJson)
      const created = await createAdminChallenge(adminKey.trim(), payload)
      setAdminChallenges(prev => [created, ...prev])
      setMessage(`Challenge “${created.title}” published.`)
      setChallengeJson(challengeExample)
      if (activeHandle) await load(activeHandle)
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Challenge JSON is invalid')
    } finally {
      setAdminLoading(false)
    }
  }

  async function archiveChallenge(id: string) {
    setAdminLoading(true)
    try {
      await archiveAdminChallenge(adminKey.trim(), id)
      setAdminChallenges(prev => prev.map(c => c.id === id ? { ...c, active: false } : c))
      setMessage('Challenge archived.')
      if (activeHandle) await load(activeHandle)
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Could not archive challenge')
    } finally {
      setAdminLoading(false)
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand" onClick={() => setTab('home')}>
          <span className="brand-mark">⚔</span>
          <div><b>CF//QUEST</b><small>Codeforces, but make it a game.</small></div>
        </div>
        <nav>
          <button className={tab === 'home' ? 'active' : ''} onClick={() => setTab('home')}>Arena</button>
          <button className={tab === 'quests' ? 'active' : ''} onClick={() => setTab('quests')}>Quests <em>{questDone}</em></button>
          <button className={tab === 'profile' ? 'active' : ''} onClick={() => setTab('profile')}>Profile</button>
          <button className={tab === 'admin' ? 'active' : ''} onClick={() => setTab('admin')}>Admin</button>
        </nav>
        <div className="sync-controls">
          <input value={handle} onChange={e => setHandle(e.target.value)} placeholder="Codeforces handle" />
          <button className="primary" onClick={connect} disabled={syncing || !handle.trim()}>{syncing ? 'Syncing…' : activeHandle ? 'Sync' : 'Start'}</button>
        </div>
      </header>

      {message && <div className="toast system-toast"><span className="system-toast-dot" />{message}<button onClick={() => setMessage('')}>×</button></div>}

      {game && tab !== 'admin' && (
        <div className="system-strip">
          <span className="system-bracket">[</span>
          <span className="system-pulse" />
          <span>SYSTEM ONLINE</span>
          <span className="system-separator" />
          <span>PLAYER // {profile?.handle}</span>
          <span className="system-separator" />
          <span>RANK // {profile?.title?.toUpperCase()}</span>
          <span className="system-bracket">]</span>
        </div>
      )}

      {tab === 'admin' ? (
        <AdminPanel
          keyValue={adminKey}
          setKeyValue={setAdminKey}
          authed={adminAuthed}
          loading={adminLoading}
          challenges={adminChallenges}
          challengeJson={challengeJson}
          setChallengeJson={setChallengeJson}
          onLogin={openAdmin}
          onAdd={addChallenge}
          onArchive={archiveChallenge}
        />
      ) : !game ? (
        <section className="landing card">
          <div className="landing-icon">⚔️</div>
          <p className="eyebrow">YOUR CODEFORCES ADVENTURE</p>
          <h1>Turn every accepted solution<br />into <span>progress.</span></h1>
          <p>Daily quests. XP. Streaks. Achievements. Your exact problem ratings—tracked like a game.</p>
          <button className="primary big" onClick={connect} disabled={syncing || !handle.trim()}>{syncing ? 'Entering the arena…' : 'Enter the arena →'}</button>
        </section>
      ) : (
        <>
          <section className="hero-grid">
            <div className="profile-card card">
              <div className="avatar">{profile?.handle.slice(0, 1).toUpperCase()}</div>
              <div className="profile-main">
                <div className="eyebrow">LEVEL {profile?.level}</div>
                <h1>{profile?.handle}</h1>
                <p>{profile?.title}</p>
                <div className="xp-track"><span style={{ width: `${Math.min(100, levelPct)}%` }} /></div>
                <div className="xp-row"><b>{profile?.level_xp} XP</b><span>{profile?.next_level_xp} XP to next level</span></div>
              </div>
              <div className="score-orb"><span className="score-label">SCORE</span><strong>{profile?.score.toLocaleString()}</strong><small>HUNTER POINTS</small></div>
            </div>

            <div className="quick-stats">
              <div className="card mini-stat"><span>🔥 STREAK</span><strong>{profile?.current_streak}</strong><small>days</small></div>
              <div className="card mini-stat"><span>✅ SOLVED</span><strong>{profile?.total_solved}</strong><small>problems</small></div>
              <div className="card mini-stat"><span>🚀 PEAK</span><strong>{profile?.max_rating_solved ?? '—'}</strong><small>rating</small></div>
              <div className="card mini-stat"><span>📅 ACTIVE</span><strong>{profile?.active_days}</strong><small>days</small></div>
            </div>
          </section>

          {tab === 'home' && <>
            <section className="section-head"><div><p className="eyebrow">TODAY'S RUN</p><h2>Daily quests</h2></div><button className="ghost" onClick={refresh}>{loading ? 'Refreshing…' : '↻ Refresh'}</button></section>
            <section className="quest-grid">{game.daily_quests.map(q => <QuestCard key={q.id} quest={q} />)}</section>

            {game.custom_challenges.length > 0 && <>
              <section className="section-head"><div><p className="eyebrow">LIVE EVENTS</p><h2>Community challenges</h2></div><span className="quest-count">{game.custom_challenges.filter(c => c.completed).length}/{game.custom_challenges.length}</span></section>
              <section className="challenge-grid">{game.custom_challenges.map(c => <CustomChallengeCard key={c.id} challenge={c} />)}</section>
            </>}

            <section className="arena-grid">
              <div className="card panel">
                <div className="panel-head"><div><p className="eyebrow">TODAY</p><h2>{selectedDate}</h2></div><input className="date-input" type="date" value={selectedDate} onChange={e => setSelectedDate(e.target.value)} /></div>
                <div className="today-banner"><strong>{day?.solved_count ?? 0}</strong><span>problems cleared today</span><div className="tiny-ring">+{game.daily_quests.filter(q => q.completed).reduce((n, q) => n + q.reward_xp, 0)} XP</div></div>
                <div className="problems">
                  {day?.problems.map(p => <a className="problem" href={p.url} target="_blank" rel="noreferrer" key={`${p.contest_id}-${p.problem_index}`}>
                    <span className={`rating r-${p.rating ? Math.min(2600, Math.max(800, p.rating)) : 'unknown'}`}>{p.rating ?? '?'}</span>
                    <div><b>{p.problem_index}. {p.name}</b><small>{p.tags.join(' · ') || 'No tags'}</small></div>
                    <span className="open">↗</span>
                  </a>)}
                  {day && day.problems.length === 0 && <div className="empty">No accepted solutions for this day yet. Your next quest awaits.</div>}
                </div>
              </div>

              <div className="card panel challenge-panel">
                <div className="eyebrow">WEEKLY CHALLENGES</div>
                <h2>Push your limits</h2>
                <p className="panel-sub">Week of {game.weekly_start}</p>
                <div className="challenge-list">{game.weekly_challenges.map(q => <ChallengeCard key={q.id} quest={q} />)}</div>
                <div className="weekly-complete"><span>{challengeDone}/3 complete</span><div><i style={{ width: `${challengeDone / 3 * 100}%` }} /></div></div>
              </div>
            </section>
          </>}

          {tab === 'quests' && <section className="quest-page">
            <section className="section-head"><div><p className="eyebrow">QUEST BOARD</p><h2>Today's missions</h2></div><span className="quest-count">{questDone}/3 cleared</span></section>
            <section className="quest-grid expanded">{game.daily_quests.map(q => <QuestCard key={q.id} quest={q} large />)}</section>
            <section className="section-head"><div><p className="eyebrow">WEEKLY</p><h2>Long-form challenges</h2></div></section>
            <section className="challenge-grid">{game.weekly_challenges.map(q => <ChallengeCard key={q.id} quest={q} large />)}</section>
            {game.custom_challenges.length > 0 && <>
              <section className="section-head"><div><p className="eyebrow">LIVE EVENTS</p><h2>Admin-created challenges</h2></div></section>
              <section className="challenge-grid">{game.custom_challenges.map(c => <CustomChallengeCard key={c.id} challenge={c} large />)}</section>
            </>}
          </section>}

          {tab === 'profile' && <section className="profile-page">
            <div className="card profile-banner">
              <div className="profile-avatar-large">{profile?.handle.slice(0, 1).toUpperCase()}</div>
              <div><p className="eyebrow">SYSTEM // PLAYER PROFILE</p><h2>{profile?.handle}</h2><p className="profile-rankline"><span>{profile?.title}</span><i /> <span>LEVEL {profile?.level}</span></p></div>
              <div className="profile-score"><span>Total Score</span><strong>{profile?.score.toLocaleString()}</strong></div>
            </div>

            <section className="section-head"><div><p className="eyebrow">ACHIEVEMENTS</p><h2>Unlocked badges</h2></div><span className="quest-count">{game.achievements.filter(a => a.unlocked).length}/{game.achievements.length}</span></section>
            <section className="achievement-grid">{game.achievements.map(a => <div key={a.id} className={`card achievement ${a.unlocked ? 'unlocked' : ''}`}>
              <div className="achievement-icon">{a.icon}</div>
              <div><h3>{a.title}</h3><p>{a.description}</p><div className="achievement-progress"><i style={{ width: `${progressPct(a.progress, a.target)}%` }} /></div><small>{a.progress} / {a.target}</small></div>
            </div>)}</section>
          </section>}
        </>
      )}
      <footer>CF//QUEST · real Codeforces history · admin-authored events · stay consistent.</footer>
    </main>
  )
}

function AdminPanel(props: {
  keyValue: string
  setKeyValue: (v: string) => void
  authed: boolean
  loading: boolean
  challenges: AdminChallenge[]
  challengeJson: string
  setChallengeJson: (v: string) => void
  onLogin: () => void
  onAdd: () => void
  onArchive: (id: string) => void
}) {
  return <section className="admin-page">
    <div className="section-head"><div><p className="eyebrow">GAME MASTER CONSOLE</p><h2>Challenge builder</h2><p className="panel-sub">Admins can publish rule-based challenges without touching the database.</p></div></div>

    <section className="admin-grid">
      <div className="card panel">
        <div className="panel-head"><div><p className="eyebrow">AUTHENTICATION</p><h2>Admin access</h2></div>{props.authed && <span className="admin-status">CONNECTED</span>}</div>
        <div className="admin-auth-row"><input type="password" value={props.keyValue} onChange={e => props.setKeyValue(e.target.value)} placeholder="ADMIN_KEY" /><button className="primary" onClick={props.onLogin} disabled={props.loading}>{props.loading ? 'Checking…' : 'Unlock'}</button></div>
        <p className="helper">The key is sent only in the <code>X-Admin-Key</code> header and kept in session storage.</p>
      </div>

      <div className="card panel">
        <div className="panel-head"><div><p className="eyebrow">STRUCTURED INPUT</p><h2>Describe the challenge</h2></div><button className="ghost" onClick={() => props.setChallengeJson(challengeExample)}>Example</button></div>
        <textarea className="json-editor" value={props.challengeJson} onChange={e => props.setChallengeJson(e.target.value)} spellCheck={false} />
        <div className="rule-help">
          <b>Supported rules</b>
          <span><code>solve_count</code> · <code>practice_days</code> · <code>hardest_rating</code></span>
          <span>Filters: <code>min_rating</code>, <code>max_rating</code>, <code>tags_any</code>, <code>tags_all</code>, <code>contest_ids</code></span>
        </div>
        <button className="primary big admin-publish" onClick={props.onAdd} disabled={!props.authed || props.loading}>{props.loading ? 'Publishing…' : '⚔ Publish challenge'}</button>
      </div>
    </section>

    <section className="section-head"><div><p className="eyebrow">CHALLENGE LOG</p><h2>Published events</h2></div><span className="quest-count">{props.challenges.length}</span></section>
    <section className="admin-challenge-list">
      {props.challenges.map(c => <div key={c.id} className={`card admin-challenge ${c.active ? '' : 'archived'}`}>
        <div className="admin-challenge-main"><div className="admin-icon">{c.icon}</div><div><h3>{c.title}</h3><p>{c.description}</p><small>{c.slug} · +{c.reward_xp} XP · {c.starts_on ?? 'open'} → {c.ends_on ?? 'open'}</small></div></div>
        <div className="admin-challenge-actions">{c.active ? <button className="danger" onClick={() => props.onArchive(c.id)} disabled={props.loading}>Archive</button> : <span className="muted-badge">ARCHIVED</span>}</div>
        <details><summary>View rule JSON</summary><pre>{JSON.stringify(c.definition, null, 2)}</pre></details>
      </div>)}
      {props.challenges.length === 0 && <div className="card empty">No challenges yet. Publish your first event above.</div>}
    </section>
  </section>
}

function QuestCard({ quest, large = false }: { quest: Game['daily_quests'][number]; large?: boolean }) {
  return <div className={`card quest-card ${quest.completed ? 'done' : ''} ${large ? 'large' : ''}`}>
    <div className="quest-top"><span className="quest-icon quest-glyph">{quest.id === 'warmup' ? '⚡' : quest.id === 'climber' ? '🧗' : '🎯'}</span><span className="quest-type">DAILY QUEST</span><span className="reward">+{quest.reward_xp} XP</span></div>
    <h3>{quest.title}</h3><p>{quest.description}</p>
    <div className="quest-progress"><div><i style={{ width: `${progressPct(quest.progress, quest.target)}%` }} /></div><span>{quest.progress}/{quest.target}</span></div>
    <div className="quest-state">{quest.completed ? '✓ QUEST CLEARED' : `${quest.target - quest.progress} more to clear`}</div>
  </div>
}

function ChallengeCard({ quest, large = false }: { quest: Game['weekly_challenges'][number]; large?: boolean }) {
  return <div className={`challenge ${quest.completed ? 'done' : ''} ${large ? 'large' : ''}`}>
    <div className="challenge-title"><div><span className="quest-icon">🏆</span><h3>{quest.title}</h3></div><b>+{quest.reward_xp}</b></div>
    <p>{quest.description}</p>
    <div className="quest-progress"><div><i style={{ width: `${progressPct(quest.progress, quest.target)}%` }} /></div><span>{quest.progress}/{quest.target}</span></div>
    <div className="quest-state">{quest.completed ? '✓ COMPLETED' : 'IN PROGRESS'}</div>
  </div>
}

function CustomChallengeCard({ challenge, large = false }: { challenge: Challenge; large?: boolean }) {
  return <div className={`challenge live-challenge ${challenge.completed ? 'done' : ''} ${large ? 'large' : ''}`}>
    <div className="challenge-title"><div><span className="quest-icon">{challenge.icon}</span><h3>{challenge.title}</h3></div><b>+{challenge.reward_xp}</b></div>
    <p>{challenge.description}</p>
    <div className="challenge-window">{challenge.starts_on ?? 'Always'} → {challenge.ends_on ?? 'Open ended'}</div>
    <div className="quest-progress"><div><i style={{ width: `${progressPct(challenge.progress, challenge.target)}%` }} /></div><span>{challenge.progress}/{challenge.target}</span></div>
    <div className="quest-state">{challenge.completed ? '✓ EVENT CLEARED' : 'LIVE EVENT'}</div>
  </div>
}

export default App
