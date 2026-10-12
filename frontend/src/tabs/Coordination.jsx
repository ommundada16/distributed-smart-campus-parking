import { useState } from 'react'
import { get, call, setCoordinatorFailure } from '../api'
import { usePolling } from '../hooks'
import Concept from '../components/Concept'
import EventLog from '../components/EventLog'

const ROLE_COLOR = { LEADER: 'online', FOLLOWER: 'available', ELECTING: 'reserved', FAILING: 'offline', DOWN: 'offline' }

export default function Coordination({ events }) {
  const [info, refresh] = usePolling(() => get('/api/coordinators'), 1000)
  const [log, setLog] = useState([])
  const [busy, setBusy] = useState(false)

  async function fire() {
    setBusy(true)
    const t0 = performance.now()
    const { data, servedBy } = await call('/api/parking/find', { method: 'POST' })
    const ms = Math.round(performance.now() - t0)
    setLog((l) => [{
      at: new Date().toLocaleTimeString(), ok: data.success, ms,
      text: data.success
        ? `${data.zone_id}/${data.slot_id} — coordinator ${data.served_by_coordinator} via ${servedBy || data.gateway}`
        : data.message,
      reservation: data.reservation_id,
    }, ...l].slice(0, 8))
    if (data.success) await call('/api/parking/release', { method: 'POST', body: { reservation_id: data.reservation_id } })
    setBusy(false)
  }

  async function toggle(id, fail) {
    await setCoordinatorFailure(id, fail)
    refresh()
  }

  const replicas = info?.replicas || []
  return (
    <>
      <Concept
        unit="Unit 3" topic="Election Algorithms (Bully) + leader beacon"
        problem="In FA-1 the coordinator was one process — a single point of failure. If it died, no parking request could be served."
      >
        Three identical coordinator replicas run. The live replica with the <b>highest id</b> becomes leader (Bully
        algorithm) and sends a <b>beacon</b> every second. Followers that miss beacons for 4 s start an election: they send
        ELECTION to higher ids; if nobody answers they announce themselves with a new <b>term</b>. A recovered ex-leader
        “bullies” its way back. Zones find the leader by <i>name</i> (WhoIsLeader), so failover needs no reconfiguration.
      </Concept>

      <section className="panel">
        <h2>Coordinator replicas</h2>
        <div className="card-grid">
          {replicas.map((r) => (
            <div className="card" key={r.id}>
              <div className="zone-card-header">
                <strong>{r.node_id}</strong>
                <span className={`badge ${ROLE_COLOR[r.role] || ''}`}>{r.role}</span>
              </div>
              <p className="muted">priority {r.id} · {r.host}:{r.port}</p>
              <table><tbody>
                <tr><td>Term</td><td>{r.term}</td></tr>
                <tr><td>Believes leader is</td><td>{r.leader_id ? `COORD_${r.leader_id}` : '—'}</td></tr>
              </tbody></table>
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button className="danger" disabled={r.state !== 'UP'} onClick={() => toggle(r.id, true)}>Kill</button>
                <button className="secondary" disabled={r.state === 'UP'} onClick={() => toggle(r.id, false)}>Recover</button>
              </div>
            </div>
          ))}
        </div>
        <p>
          Current leader: <b>{info?.leader || 'none — election in progress'}</b>{info?.term ? ` (term ${info.term})` : ''}
        </p>
      </section>

      <section className="panel">
        <h2>Try it: kill the leader, keep requesting</h2>
        <ol className="muted">
          <li>Press <b>Kill</b> on the LEADER card above.</li>
          <li>Press “Request a slot” repeatedly: requests fail for a few seconds while the survivors elect a new leader, then succeed — served by a different coordinator.</li>
          <li>Press <b>Recover</b>: the old (higher-id) node returns, bullies its way back and the term increases.</li>
        </ol>
        <button onClick={fire} disabled={busy}>{busy ? 'Requesting…' : 'Request a slot (then release it)'}</button>
        <table style={{ marginTop: 12 }}>
          <tbody>
            {log.map((l, i) => (
              <tr key={i}>
                <td className="muted">{l.at}</td>
                <td><span className={`badge ${l.ok ? 'online' : 'offline'}`}>{l.ok ? 'OK' : 'FAILED'}</span></td>
                <td>{l.text}</td><td className="muted">{l.ms} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <h2>Election &amp; failure timeline</h2>
        <EventLog
          events={events} limit={20} showClocks
          filter={(e) => ['LEADER_ELECTED', 'LEADER_LOST'].includes(e.event) || (e.event.startsWith('NODE_') && e.data?.role === 'coordinator')}
        />
      </section>
    </>
  )
}
