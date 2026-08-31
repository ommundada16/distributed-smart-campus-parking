import { useState } from 'react'
import { setZoneFailure } from '../api'
import { useApp } from '../context'
import StatusBadge from '../components/StatusBadge'
import EventLog from '../components/EventLog'

export default function SystemMonitor() {
  const { systemStatus, events, refreshStatus } = useApp()
  const [busyZone, setBusyZone] = useState(null)

  async function toggleFailure(zoneKey, simulate) {
    setBusyZone(zoneKey)
    try {
      await setZoneFailure(zoneKey, simulate)
      setTimeout(refreshStatus, 500)
    } finally {
      setBusyZone(null)
    }
  }

  return (
    <div>
      <h2>System Monitor</h2>
      <p className="muted">Live status pulled from the coordinator's node registry over gRPC — nothing here is hardcoded.</p>

      <div className="panel">
        <h3>Services</h3>
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
            {(systemStatus.zones || []).map((z) => (
              <tr key={z.node_id}>
                <td>{z.service}</td><td>{z.node_id}</td><td>{z.port}</td>
                <td><StatusBadge status={z.status} /></td>
                <td className="muted">{z.last_heartbeat ? new Date(z.last_heartbeat).toLocaleTimeString() : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h3>Fault Tolerance Demonstration</h3>
        <p className="muted">
          These buttons make the real zone process stop sending heartbeats and reject RPCs —
          the coordinator detects it via its normal heartbeat timeout, the same as a real crash.
        </p>
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 12 }}>
          {(systemStatus.zones || []).map((z) => {
            const zoneKey = z.zone_id.slice(-1)
            const isOffline = z.status === 'OFFLINE'
            return (
              <div key={z.node_id} className="card" style={{ minWidth: 200 }}>
                <div className="zone-card-header">
                  <strong>{z.node_id}</strong>
                  <StatusBadge status={z.status} />
                </div>
                <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
                  <button className="danger" disabled={isOffline || busyZone === zoneKey}
                    onClick={() => toggleFailure(zoneKey, true)}>
                    Fail
                  </button>
                  <button className="secondary" disabled={!isOffline || busyZone === zoneKey}
                    onClick={() => toggleFailure(zoneKey, false)}>
                    Recover
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="panel">
        <h3>Event Activity (Redis Streams → WebSocket)</h3>
        <EventLog events={events} limit={30} />
      </div>
    </div>
  )
}
