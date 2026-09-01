import { useEffect, useState } from 'react'
import {
  connectEventStream, findParking, getRecentEvents, getSystemStatus,
  releaseParking, setZoneFailure,
} from './api'
import StatusBadge from './components/StatusBadge'
import EventLog from './components/EventLog'

const STATUS_TRIGGERING_EVENTS = new Set([
  'NODE_REGISTERED', 'NODE_FAILED', 'NODE_RECOVERED',
  'PARKING_RESERVED', 'PARKING_RELEASED', 'SLOT_STATUS_CHANGED',
])

export default function App() {
  const [systemStatus, setSystemStatus] = useState({ services: [], zones: [] })
  const [events, setEvents] = useState([])
  const [reservation, setReservation] = useState(() => {
    const saved = localStorage.getItem('activeReservation')
    return saved ? JSON.parse(saved) : null
  })
  const [finding, setFinding] = useState(false)
  const [findResult, setFindResult] = useState(null)
  const [busyZone, setBusyZone] = useState(null)

  async function refreshStatus() {
    try {
      setSystemStatus(await getSystemStatus())
    } catch {
      // gateway unreachable — keep last-known status on screen
    }
  }

  useEffect(() => {
    refreshStatus()
    getRecentEvents(20).then((data) => setEvents(data.events || []))

    const socket = connectEventStream((event) => {
      setEvents((prev) => [event, ...prev].slice(0, 100))
      if (STATUS_TRIGGERING_EVENTS.has(event.event)) refreshStatus()
    })
    const pollId = setInterval(refreshStatus, 5000)

    return () => {
      socket.close()
      clearInterval(pollId)
    }
  }, [])

  function saveReservation(value) {
    setReservation(value)
    if (value) localStorage.setItem('activeReservation', JSON.stringify(value))
    else localStorage.removeItem('activeReservation')
  }

  async function handleFindParking() {
    setFinding(true)
    setFindResult(null)
    try {
      const data = await findParking()
      setFindResult(data)
      if (data.success) {
        saveReservation({
          zone_id: data.zone_id, slot_id: data.slot_id, reservation_id: data.reservation_id,
        })
      }
    } finally {
      setFinding(false)
    }
  }

  async function handleRelease() {
    const data = await releaseParking(reservation.reservation_id)
    if (data.success) saveReservation(null)
  }

  async function toggleFailure(zoneKey, simulate) {
    setBusyZone(zoneKey)
    try {
      await setZoneFailure(zoneKey, simulate)
      setTimeout(refreshStatus, 500)
    } finally {
      setBusyZone(null)
    }
  }

  const zones = systemStatus.zones || []
  const totals = zones.reduce(
    (acc, z) => ({
      total: acc.total + z.total_slots,
      available: acc.available + z.available_slots,
      occupied: acc.occupied + z.occupied_slots,
      reserved: acc.reserved + z.reserved_slots,
    }),
    { total: 0, available: 0, occupied: 0, reserved: 0 }
  )
  const onlineCount = zones.filter((z) => z.status === 'ONLINE').length

  return (
    <div className="page">
      <header className="page-header">
        <h1>Distributed Smart Campus Parking System</h1>
        <p className="muted">
          Client → API Gateway (HTTP/WebSocket) → Coordinator (gRPC) → Zone A/B/C (gRPC + P2P) → Redis Streams → back.
        </p>
      </header>

      <section className="panel">
        <h2>1. Live Snapshot</h2>
        <div className="card-grid">
          <div className="card"><div className="value">{totals.total}</div><div className="label">Total Slots</div></div>
          <div className="card"><div className="value">{totals.available}</div><div className="label">Available</div></div>
          <div className="card"><div className="value">{totals.occupied}</div><div className="label">Occupied</div></div>
          <div className="card"><div className="value">{totals.reserved}</div><div className="label">Reserved</div></div>
          <div className="card"><div className="value">{onlineCount} / {zones.length}</div><div className="label">Zones Online</div></div>
        </div>
      </section>

      <section className="panel">
        <h2>2. Parking Zones — independent processes, each with its own gRPC + TCP ports</h2>
        <div className="card-grid">
          {zones.map((z) => {
            const zoneKey = z.zone_id.slice(-1)
            const isOffline = z.status === 'OFFLINE'
            return (
              <div className="card" key={z.node_id}>
                <div className="zone-card-header">
                  <strong>{z.zone_id}</strong>
                  <StatusBadge status={z.status} />
                </div>
                <p className="muted">{z.node_id} · gRPC {z.port}</p>
                <table>
                  <tbody>
                    <tr><td>Available</td><td>{z.available_slots}</td></tr>
                    <tr><td>Occupied</td><td>{z.occupied_slots}</td></tr>
                    <tr><td>Reserved</td><td>{z.reserved_slots}</td></tr>
                  </tbody>
                </table>
                <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                  <button className="danger" disabled={isOffline || busyZone === zoneKey}
                    onClick={() => toggleFailure(zoneKey, true)}>Fail</button>
                  <button className="secondary" disabled={!isOffline || busyZone === zoneKey}
                    onClick={() => toggleFailure(zoneKey, false)}>Recover</button>
                </div>
              </div>
            )
          })}
        </div>
        <p className="muted" style={{ marginTop: 8 }}>
          Fail/Recover make the real zone process stop sending heartbeats and reject RPCs — the coordinator
          detects it through its normal heartbeat timeout, exactly as it would for a real crash.
        </p>
      </section>

      <section className="panel">
        <h2>3. Find &amp; Reserve Parking (RPC)</h2>
        <p className="muted">Request path: Browser → Gateway → Coordinator → gRPC → a Parking Zone → back.</p>
        <button onClick={handleFindParking} disabled={finding}>
          {finding ? 'Searching...' : 'Find Parking'}
        </button>

        {findResult && findResult.success && (
          <table style={{ marginTop: 16, maxWidth: 420 }}>
            <tbody>
              <tr><td>Recommended Zone</td><td>{findResult.zone_id}</td></tr>
              <tr><td>Slot ID</td><td>{findResult.slot_id}</td></tr>
              <tr><td>Reservation ID</td><td>{findResult.reservation_id}</td></tr>
            </tbody>
          </table>
        )}
        {findResult && !findResult.success && (
          <p style={{ color: 'var(--red)', marginTop: 16 }}>{findResult.message}</p>
        )}

        {reservation && (
          <div className="reservation-box" style={{ marginTop: 20 }}>
            <h3>Active Reservation</h3>
            <p style={{ fontSize: 22, fontWeight: 700 }}>{reservation.zone_id} · {reservation.slot_id}</p>
            <p className="muted">{reservation.reservation_id}</p>
            <button className="danger" onClick={handleRelease} style={{ marginTop: 12 }}>Release Slot</button>
          </div>
        )}
      </section>

      <section className="panel">
        <h2>4. System Monitor — live from the coordinator's node registry</h2>
        <table>
          <thead>
            <tr><th>Service</th><th>Node ID</th><th>Port</th><th>Status</th><th>Last Heartbeat</th></tr>
          </thead>
          <tbody>
            {(systemStatus.services || []).map((s) => (
              <tr key={s.node_id}>
                <td>{s.service}</td><td>{s.node_id}</td><td>{s.port}</td>
                <td><StatusBadge status={s.status} /></td><td>—</td>
              </tr>
            ))}
            {zones.map((z) => (
              <tr key={z.node_id}>
                <td>Zone {z.zone_id.slice(-1)}</td><td>{z.node_id}</td><td>{z.port}</td>
                <td><StatusBadge status={z.status} /></td>
                <td className="muted">{z.last_heartbeat ? new Date(z.last_heartbeat).toLocaleTimeString() : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <h2>5. Live Communication Activity</h2>
        <p className="muted">
          Every RPC call, P2P exchange, and message-bus event shows up here the instant it happens,
          pushed over the WebSocket connection — nothing on this page is polled-and-guessed.
        </p>
        <EventLog events={events} limit={30} />
      </section>
    </div>
  )
}
