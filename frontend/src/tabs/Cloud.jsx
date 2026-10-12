import { useState } from 'react'
import { call, get, post } from '../api'
import { useAction, usePolling } from '../hooks'
import Concept, { Bar, Verdict } from '../components/Concept'
import StatusBadge from '../components/StatusBadge'

export default function Cloud({ systemStatus }) {
  return (
    <>
      <Concept
        unit="Unit 4" topic="Emerging distributed paradigms — deployment, web-scale delivery, serverless, MapReduce"
        problem="“How many servers do you have, what are their configurations, and how is load balanced?”"
      >
        The whole system runs as <b>real containers</b> — each with its own hostname and a CPU/memory limit — under Docker Compose, with equivalent
        Kubernetes manifests in <code>k8s/</code>. Below: the live deployment table, the edge/load-balancing layer, a serverless platform and a MapReduce batch job.
      </Concept>
      <Deployment systemStatus={systemStatus} />
      <EdgeAndBalancing />
      <Serverless />
      <MapReduce />
    </>
  )
}

function Deployment({ systemStatus }) {
  const [topo] = usePolling(() => get('/api/nodes'), 60000)
  const live = {}
  ;(systemStatus.services || []).forEach((s) => { live[s.node_id] = s.status })
  ;(systemStatus.zones || []).forEach((z) => { live[z.node_id] = z.status })
  const nodes = topo?.nodes || []

  return (
    <section className="panel">
      <h2>Deployment — servers and their configuration</h2>
      <table>
        <thead><tr><th>Node</th><th>Role</th><th>Replicas</th><th>CPU limit</th><th>Memory limit</th><th>Image / runtime</th><th>Port(s)</th></tr></thead>
        <tbody>
          {nodes.map((n) => (
            <tr key={n.name}>
              <td><b>{n.name}</b></td><td>{n.role}</td><td>{n.replicas}</td><td>{n.cpu}</td><td>{n.memory}</td>
              <td className="small">{n.image}</td><td>{n.ports}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">Declared in <code>docker-compose.yml</code> (<code>deploy.resources.limits</code>) and <code>k8s/*.yaml</code> (<code>resources.limits</code>). Live status of each running node:</p>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {Object.entries(live).map(([id, st]) => (
          <span key={id} className="chip">{id} <StatusBadge status={st} /></span>
        ))}
      </div>
    </section>
  )
}

function EdgeAndBalancing() {
  const [spread, setSpread] = useState(null)
  const [edge, setEdge] = useState([])
  const [busy, setBusy] = useState(false)

  async function probeBalance() {
    setBusy(true)
    const tally = {}
    for (let i = 0; i < 12; i++) {
      const { servedBy } = await call(`/api/whoami?i=${i}`)
      tally[servedBy || 'unknown'] = (tally[servedBy || 'unknown'] || 0) + 1
    }
    setSpread(tally)
    setBusy(false)
  }

  async function probeEdge() {
    const { data, cache, servedBy } = await call('/api/edge/summary')
    setEdge((e) => [{ at: new Date().toLocaleTimeString(), cache: cache || 'n/a (no edge in front)', servedBy, age: data.generated_at ? Math.round(Date.now() / 1000 - data.generated_at) : null, available: data.available }, ...e].slice(0, 6))
  }

  return (
    <section className="panel">
      <h2>Web-scale delivery — load balancer &amp; edge cache (Nginx)</h2>
      <div className="grid2">
        <div>
          <h3>Request load balancing</h3>
          <p className="muted">12 requests through the Nginx entry point; Nginx round-robins across the gateway replicas. Each response carries the replica's name.</p>
          <button onClick={probeBalance} disabled={busy}>{busy ? 'Sending…' : 'Send 12 requests'}</button>
          {spread && Object.entries(spread).map(([name, n]) => <Bar key={name} label={name} value={n} max={12} />)}
          {spread && Object.keys(spread).length === 1 && <p className="muted">Only one gateway answered — you are running the local single-gateway mode. Under Docker Compose there are two.</p>}
        </div>
        <div>
          <h3>Edge cache (CDN-style)</h3>
          <p className="muted">/api/edge/summary is identical for every visitor, so the edge caches it for 5 s: the first call is a MISS, repeats are HITs served without touching the backend.</p>
          <button onClick={probeEdge}>Fetch public availability</button>
          <table><tbody>
            {edge.map((e, i) => (
              <tr key={i}><td className="muted">{e.at}</td>
                <td><span className={`badge ${String(e.cache).toUpperCase() === 'HIT' ? 'online' : 'reserved'}`}>{e.cache}</span></td>
                <td>{e.available} free</td><td className="muted">data age {e.age}s · {e.servedBy}</td></tr>
            ))}
          </tbody></table>
        </div>
      </div>
    </section>
  )
}

function Serverless() {
  const [fns, refresh] = usePolling(() => get('/api/faas/functions'), 2000)
  const [occ, setOcc] = useState(0.7)
  const [invoke, iState] = useAction(() => post('/api/faas/invoke/pricing', { zone: 'A', occupancy: occ, hour: 9 }))
  const [evict] = useAction(() => post('/api/faas/evict/pricing'))
  const d = iState.data

  return (
    <section className="panel">
      <h2>Serverless — Function-as-a-Service (AWS Lambda / Cloudflare Workers model)</h2>
      <p className="muted">
        Dynamic pricing and receipts are stateless <code>handler(event, context)</code> functions run by a local FaaS platform:
        <b> cold start</b> on first call, <b>warm</b> afterwards, <b>scale to zero</b> after 30 s idle, billed per millisecond.
        The coordinator calls <code>pricing</code> on every reservation.
      </p>
      <table>
        <thead><tr><th>Function</th><th>State</th><th>Invocations</th><th>Cold starts</th><th>Avg ms</th><th>Billed ms</th><th>GB-seconds</th><th>Idle</th></tr></thead>
        <tbody>
          {(fns?.functions || []).map((f) => (
            <tr key={f.name}>
              <td><b>{f.name}</b></td>
              <td><span className={`badge ${f.state === 'WARM' ? 'online' : 'reserved'}`}>{f.state}</span></td>
              <td>{f.invocations}</td><td>{f.cold_starts}</td><td>{f.avg_ms}</td><td>{f.billed_ms}</td><td>{f.gb_seconds}</td>
              <td>{f.idle_seconds ?? '—'} s</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 12, flexWrap: 'wrap' }}>
        <label>Zone occupancy {Math.round(occ * 100)}% <input type="range" min="0" max="1" step="0.05" value={occ} onChange={(e) => setOcc(+e.target.value)} /></label>
        <button onClick={async () => { await invoke(); refresh() }}>Invoke pricing()</button>
        <button className="danger" onClick={async () => { await evict(); refresh() }}>Evict (force scale-to-zero)</button>
      </div>
      {d && d.result && (
        <Verdict good={!d.cold_start}>
          {d.cold_start ? 'COLD start' : 'WARM start'} · {d.duration_ms} ms · billed {d.billed_ms} ms →
          ₹{d.result.price_per_hour}/hr (surge ×{d.result.surge_multiplier}, peak ×{d.result.peak_multiplier})
        </Verdict>
      )}
    </section>
  )
}

function MapReduce() {
  const [job, setJob] = useState('peak_hours')
  const [n, setN] = useState(500000)
  const [source, setSource] = useState('synthetic')
  const [run, state] = useAction((workers) => post(`/api/analytics/run?job=${job}&source=${source}&n=${n}&workers=${workers}`))
  const [history, setHistory] = useState([])
  const d = state.data

  async function go(workers) {
    const r = await run(workers)
    if (r && !r.error) setHistory((h) => [{ workers, ms: r.stats.total_ms, map: r.stats.map_ms, n: r.stats.input_records }, ...h].slice(0, 6))
  }

  const histMax = d && d.job === 'peak_hours' ? Math.max(...Object.values(d.result).flatMap((z) => z.histogram)) : 0

  return (
    <section className="panel">
      <h2>Batch analytics — MapReduce (Apache Hadoop model)</h2>
      <p className="muted">
        input split → <b>map</b> (per split, in parallel worker processes) → <b>combine</b> (local pre-aggregation) → <b>shuffle</b> (partition by key hash) → <b>reduce</b>.
        The combiner is what keeps shuffle traffic small — compare “pairs emitted” with “pairs shuffled”.
      </p>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <select value={job} onChange={(e) => setJob(e.target.value)}>
          <option value="peak_hours">Peak hours per zone</option>
          <option value="zone_load">Bookings per zone</option>
          <option value="avg_duration">Average stay per zone</option>
        </select>
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="synthetic">Synthetic demand</option>
          <option value="ledger">Real ledger history</option>
        </select>
        {source === 'synthetic' && (
          <select value={n} onChange={(e) => setN(+e.target.value)}>
            <option value="100000">100k records</option><option value="500000">500k records</option><option value="1500000">1.5M records</option>
          </select>
        )}
        <button onClick={() => go(1)} disabled={state.loading}>Run on 1 worker</button>
        <button onClick={() => go(4)} disabled={state.loading}>Run on 4 workers</button>
      </div>
      {state.loading && <p className="muted">Running…</p>}
      {d && d.error && <Verdict good={false}>{d.error}</Verdict>}
      {d && !d.error && (
        <>
          <h3>{d.title}</h3>
          <table>
            <tbody>
              <tr><td>Input records</td><td>{d.stats.input_records.toLocaleString()}</td><td>Map tasks / reduce tasks</td><td>{d.stats.map_tasks} / {d.stats.reduce_tasks}</td></tr>
              <tr><td>Pairs emitted by mappers</td><td>{d.stats.pairs_emitted_by_mappers.toLocaleString()}</td><td>Pairs shuffled (after combiner)</td><td>{d.stats.pairs_shuffled_after_combiner.toLocaleString()} <b>(−{d.stats.shuffle_reduction_pct}%)</b></td></tr>
              <tr><td>Map / shuffle / reduce</td><td>{d.stats.map_ms} / {d.stats.shuffle_ms} / {d.stats.reduce_ms} ms</td><td>Total</td><td><b>{d.stats.total_ms} ms</b> on {d.workers} worker(s)</td></tr>
            </tbody>
          </table>
          {d.job === 'peak_hours' ? Object.entries(d.result).map(([zone, v]) => (
            <div key={zone} style={{ marginTop: 14 }}>
              <b>{zone}</b> — peak hour <b>{v.peak_hour}:00</b>
              <div className="hist">
                {v.histogram.map((c, h) => (
                  <div key={h} className="hist-col" title={`${h}:00 — ${c} bookings`}>
                    <div className="hist-bar" style={{ height: `${histMax ? (100 * c) / histMax : 0}%`, background: h === v.peak_hour ? '#d9412e' : 'var(--primary)' }} />
                    <span>{h}</span>
                  </div>
                ))}
              </div>
            </div>
          )) : (
            <table style={{ marginTop: 12 }}><tbody>
              {Object.entries(d.result).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}
            </tbody></table>
          )}
        </>
      )}
      {history.length > 1 && (
        <p className="muted">Run history: {history.map((h) => `${h.workers}w=${h.ms}ms`).join(' · ')}</p>
      )}
    </section>
  )
}
