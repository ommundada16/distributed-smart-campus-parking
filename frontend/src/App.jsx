import { useEffect, useState } from 'react'
import { connectEventStream, getRecentEvents, getSystemStatus } from './api'
import Overview from './tabs/Overview'
import Coordination from './tabs/Coordination'
import Clocks from './tabs/Clocks'
import Mutex from './tabs/Mutex'
import Snapshot from './tabs/Snapshot'
import Ledger from './tabs/Ledger'
import LoadBalancing from './tabs/LoadBalancing'
import Cloud from './tabs/Cloud'

const STATUS_TRIGGERING_EVENTS = new Set([
  'NODE_REGISTERED', 'NODE_FAILED', 'NODE_RECOVERED', 'PARKING_RESERVED', 'PARKING_RELEASED',
  'SLOT_STATUS_CHANGED', 'LEADER_ELECTED', 'FLEX_RECEIVED',
])

const TABS = [
  { id: 'overview', label: 'Overview', unit: 'FA-1' },
  { id: 'coordination', label: 'Leader Election', unit: 'Unit 3' },
  { id: 'clocks', label: 'Clocks', unit: 'Unit 3' },
  { id: 'mutex', label: 'Mutual Exclusion', unit: 'Unit 3' },
  { id: 'snapshot', label: 'Global Snapshot', unit: 'Unit 3' },
  { id: 'ledger', label: 'Ledger', unit: 'Unit 4' },
  { id: 'balance', label: 'Load Balancing', unit: 'Units 1/4' },
  { id: 'cloud', label: 'Cloud & Deployment', unit: 'Unit 4' },
]

function initialTab() {
  const hash = window.location.hash.replace('#', '')
  return TABS.some((t) => t.id === hash) ? hash : 'overview'
}

export default function App() {
  const [tab, setTab] = useState(initialTab)
  const [systemStatus, setSystemStatus] = useState({ services: [], zones: [] })
  const [events, setEvents] = useState([])

  async function refreshStatus() {
    try {
      setSystemStatus(await getSystemStatus())
    } catch {
      // gateway unreachable — keep last-known status on screen
    }
  }

  useEffect(() => {
    refreshStatus()
    getRecentEvents(40).then((data) => setEvents([...(data.events || [])].reverse()))
    const socket = connectEventStream((event) => {
      setEvents((prev) => [event, ...prev].slice(0, 200))
      if (STATUS_TRIGGERING_EVENTS.has(event.event)) refreshStatus()
    })
    const pollId = setInterval(refreshStatus, 4000)
    return () => {
      socket.close()
      clearInterval(pollId)
    }
  }, [])

  useEffect(() => {
    const onHash = () => setTab(initialTab())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  function selectTab(id) {
    setTab(id)
    window.history.replaceState(null, '', `#${id}`)
  }

  const leader = (systemStatus.services || []).find((s) => s.role === 'LEADER')

  return (
    <div className="page">
      <header className="page-header">
        <h1>Distributed Smart Campus Parking System <span className="fa2">FA-2</span></h1>
        <p className="muted">
          Browser → Nginx (load balancer + edge cache) → Gateway replicas → <b>elected</b> Coordinator → Zones A/B/C
          · Redis Streams · replicated ledger · serverless functions · MapReduce
        </p>
        <div className="chips">
          <span className="chip">Leader: <b>{leader ? leader.node_id : 'electing…'}</b>{leader ? ` (term ${leader.term})` : ''}</span>
          <span className="chip">Allocation policy: <b>{systemStatus.policy || '—'}</b></span>
          <span className="chip">Gateway: <b>{systemStatus.gateway || '—'}</b></span>
          <span className="chip">Zones online: <b>{(systemStatus.zones || []).filter((z) => z.status === 'ONLINE').length}/3</b></span>
        </div>
      </header>

      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={`tab ${tab === t.id ? 'active' : ''}`} onClick={() => selectTab(t.id)}>
            {t.label}<small>{t.unit}</small>
          </button>
        ))}
      </nav>

      {tab === 'overview' && <Overview systemStatus={systemStatus} events={events} refreshStatus={refreshStatus} />}
      {tab === 'coordination' && <Coordination events={events} />}
      {tab === 'clocks' && <Clocks events={events} />}
      {tab === 'mutex' && <Mutex />}
      {tab === 'snapshot' && <Snapshot />}
      {tab === 'ledger' && <Ledger />}
      {tab === 'balance' && <LoadBalancing />}
      {tab === 'cloud' && <Cloud systemStatus={systemStatus} />}
    </div>
  )
}
