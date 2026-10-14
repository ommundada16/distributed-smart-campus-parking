import { useState } from 'react'
import { findParking, releaseParking, setZoneFailure } from '../api'
import StatusBadge from '../components/StatusBadge'
import EventLog from '../components/EventLog'

export default function Overview({ systemStatus, events, refreshStatus }) {
  const [reservation, setReservation] = useState(() => {
    try {
      const saved = localStorage.getItem('activeReservation')
      return saved ? JSON.parse(saved) : null
    } catch {
      return null
    }
  })
  const [finding, setFinding] = useState(false)
  const [findResult, setFindResult] = useState(null)
  const [busyZone, setBusyZone] = useState(null)

  function saveReservation(value) {
    setReservation(value)
    try {
      if (value) localStorage.setItem('activeReservation', JSON.stringify(value))
      else localStorage.removeItem('activeReservation')
    } catch {
      // storage unavailable — keep it in memory only
    }
  }

  async function handleFindParking() {
    setFinding(true)
    setFindResult(null)
    try {
      const data = await findParking()
      setFindResult(data)
      if (data.success) {
        saveReservation({ zone_id: data.zone_id, slot_id: data.slot_id, reservation_id: data.reservation_id })
      }
    } finally {
      setFinding(false)
    }
  }

  async function handleRelease() {
    const data = await releaseParking(reservation.reservation_id)
    if (data.success) saveReservation(null)
    refreshStatus()
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
    <>
      <section className="panel">
        <h2>Live Snapshot</h2>
        <div className="card-grid">
          <div className="card"><div className="value">{totals.total}</div><div className="label">Total Slots</div></div>
          <div className="card"><div className="value">{totals.available}</div><div className="label">Available</div></div>
          <div className="card"><div className="value">{totals.occupied}</div><div className="label">Occupied</div></div>
          <div className="card"><div className="value">{totals.reserved}</div><div className="label">Reserved</div></div>
          <div className="card"><div className="value">{onlineCount} / {zones.length}</div><div className="label">Zones Online</div></div>
        </div>
        {zones.length === 0 && (
          <p className="muted">No zones registered — if the coordinator leader was just killed, a new one is being elected.</p>
        )}
      </section>

      <section className="panel">
        <h2>Parking Zones — independent processes (FA-1 fault tolerance)</h2>
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
                <p className="muted">{z.node_id} · {z.host}:{z.port}</p>
                <table>
                  <tbody>
                    <tr><td>Available</td><td>{z.available_slots}</td></tr>
                    <tr><td>Occupied</td><td>{z.occupied_slots}</td></tr>
                    <tr><td>Reserved</td><td>{z.reserved_slots}</td></tr>
                    <tr><td>Ledger blocks</td><td>{z.ledger_length}</td></tr>
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
        <p className="muted">
          Fail makes the real zone process stop heartbeating and reject RPCs. The leader detects it through
          the heartbeat timeout; on Recover the zone re-registers and <b>catches its ledger copy up</b> from peers.
        </p>
      </section>

      <section className="panel">
        <h2>Find &amp; Reserve Parking</h2>
        <p className="muted">
          Browser → Nginx → Gateway → <b>elected coordinator</b> → allocation policy → Zone (gRPC) → ledger commit
          to all zones → serverless price quote. When every zone is full, a zone books the shared overflow lot
          under Ricart-Agrawala mutual exclusion.
        </p>
        <button onClick={handleFindParking} disabled={finding}>{finding ? 'Searching...' : 'Find Parking'}</button>

        {findResult && findResult.success && (
          <table style={{ marginTop: 16, maxWidth: 560 }}>
            <tbody>
              <tr><td>Zone / Slot</td><td>{findResult.zone_id} · {findResult.slot_id}</td></tr>
              <tr><td>Reservation ID</td><td>{findResult.reservation_id}</td></tr>
              <tr><td>Allocation policy</td><td>{findResult.policy}</td></tr>
              <tr><td>Price (serverless)</td><td>₹{findResult.price_per_hour}/hr <span className="muted">— {findResult.price_source}</span></td></tr>
              <tr><td>Ledger block</td><td>#{findResult.ledger_block}</td></tr>
              <tr><td>Receipt</td><td>{findResult.receipt || '—'}</td></tr>
              <tr><td>Served by</td><td>{findResult.gateway} → {findResult.served_by_coordinator} (Lamport {findResult.lamport})</td></tr>
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
        <h2>System Monitor — every node in the deployment</h2>
        <table>
          <thead>
            <tr><th>Service</th><th>Node</th><th>Address</th><th>Role</th><th>Status</th><th>Last Heartbeat</th></tr>
          </thead>
          <tbody>
            {(systemStatus.services || []).map((s) => (
              <tr key={s.node_id}>
                <td>{s.service}</td><td>{s.node_id}</td><td>{s.host}:{s.port}</td>
                <td>{s.role || '—'}{s.role === 'LEADER' ? ` (term ${s.term})` : ''}</td>
                <td><StatusBadge status={s.status} /></td><td>—</td>
              </tr>
            ))}
            {zones.map((z) => (
              <tr key={z.node_id}>
                <td>Zone {z.zone_id.slice(-1)}</td><td>{z.node_id}</td><td>{z.host}:{z.port}</td><td>slot service</td>
                <td><StatusBadge status={z.status} /></td>
                <td className="muted">{z.last_heartbeat ? new Date(z.last_heartbeat).toLocaleTimeString() : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <h2>Live Communication Activity</h2>
        <p className="muted">
          RPC calls, P2P exchanges and message-bus events, pushed over WebSocket. <b>L=</b> is the event's
          Lamport timestamp.
        </p>
        <EventLog events={events} limit={30} showClocks />
      </section>
    </>
  )
}
