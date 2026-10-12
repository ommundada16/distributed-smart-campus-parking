import { get, post } from '../api'
import { useAction, usePolling } from '../hooks'
import Concept, { Bar } from '../components/Concept'

const POLICY_INFO = {
  first_fit: 'FA-1 baseline: walk zones in order, take the first with space. Piles load on Zone A until it is full.',
  round_robin: 'Rotate the starting zone each request. Spreads requests evenly, ignores how full each zone already is.',
  least_loaded: 'Choose the zone with the lowest occupancy. Steers traffic away from nearly-full zones.',
}
const COLORS = { first_fit: '#d9412e', round_robin: '#c98a12', least_loaded: '#1f9d55' }

export default function LoadBalancing() {
  const [policy, refresh] = usePolling(() => get('/api/policy'), 3000)
  const [setPolicy] = useAction((p) => post('/api/policy', { policy: p }))
  const [compare, cState] = useAction(() => post('/api/loadtest/compare?n=24'))
  const d = cState.data

  return (
    <>
      <Concept
        unit="Units 1 & 4" topic="Load balancing — design issues (scalability) and the paradigms that depend on it"
        problem="FA-1 used first-come-first-fit, so Zone A took every request until full while B and C sat idle — a hotspot."
      >
        There are <b>two levels</b> of balancing here. <b>(1) Application-level</b> (this tab): the coordinator leader picks the zone with a
        pluggable policy. <b>(2) Request-level</b> (Cloud tab): Nginx spreads HTTP requests across two gateway replicas
        (round-robin), and Kubernetes does the same across pods. Zones start unevenly full (A 45%, B 25%, C 10%) so the policies behave differently.
      </Concept>

      <section className="panel">
        <h2>Active allocation policy</h2>
        <div className="card-grid">
          {(policy?.options || ['first_fit', 'round_robin', 'least_loaded']).map((p) => (
            <div key={p} className={`card selectable ${policy?.policy === p ? 'selected' : ''}`}
              onClick={async () => { await setPolicy(p); refresh() }}>
              <strong>{p}</strong>{policy?.policy === p && <span className="badge online" style={{ marginLeft: 8 }}>ACTIVE</span>}
              <p className="muted">{POLICY_INFO[p]}</p>
            </div>
          ))}
        </div>
        <p className="muted">The choice is stored in Redis, so every coordinator replica and gateway sees it — a new leader keeps the same policy.</p>
      </section>

      <section className="panel">
        <h2>Compare the policies on the same burst of 24 requests</h2>
        <button onClick={() => compare()} disabled={cState.loading}>
          {cState.loading ? 'Running 3 × 24 requests (each is reserved, then released)…' : 'Run comparison'}
        </button>
        {d && d.results && d.results.map((r) => (
          <div key={r.policy} style={{ marginTop: 22 }}>
            <h3><span style={{ color: COLORS[r.policy] }}>●</span> {r.policy}</h3>
            <div className="grid2">
              <div>
                <p className="muted">Slots allocated per zone</p>
                {['PARKING_A', 'PARKING_B', 'PARKING_C'].map((z) => (
                  <Bar key={z} label={z} value={r.per_zone[z] || 0} max={r.requests} color={COLORS[r.policy]} />
                ))}
              </div>
              <div>
                <p className="muted">Occupancy after the burst (%)</p>
                {['PARKING_A', 'PARKING_B', 'PARKING_C'].map((z) => (
                  <Bar key={z} label={z} value={r.occupancy_after_pct[z]} max={100} color={r.occupancy_after_pct[z] >= 95 ? '#d9412e' : COLORS[r.policy]} />
                ))}
              </div>
            </div>
            <p>
              Imbalance (std-dev of occupancy): <b>{r.imbalance_stddev}</b> · fullest zone: <b>{r.max_occupancy_pct}%</b> · avg latency {r.avg_latency_ms} ms
            </p>
          </div>
        ))}
        {d && d.results && (
          <p className="muted" style={{ marginTop: 14 }}>
            Lower imbalance and a lower “fullest zone” mean better balance. first_fit saturates Zone A; least_loaded
            equalises occupancy so no zone becomes a hotspot or a single point of congestion.
          </p>
        )}
      </section>
    </>
  )
}
