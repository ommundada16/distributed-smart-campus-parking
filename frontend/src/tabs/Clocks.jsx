import { useState } from 'react'
import { get, post } from '../api'
import { compareVC, fmtClock, fmtVC, useAction, usePolling } from '../hooks'
import Concept, { Verdict } from '../components/Concept'

export default function Clocks({ events }) {
  const [clocks, refresh] = usePolling(() => get('/api/clocks'), 1500)
  const [sync, syncState] = useAction(() => post('/api/clocks/sync'))
  const [reskew, reskewState] = useAction(() => post('/api/clocks/skew'))
  const [sortBy, setSortBy] = useState('lamport')
  const [picked, setPicked] = useState([])

  const rows = clocks?.rows || []
  const stamped = events.filter((e) => e.lamport != null && e.node_time).slice(0, 14)
  const sorted = [...stamped].sort((a, b) =>
    sortBy === 'lamport' ? a.lamport - b.lamport : new Date(a.node_time) - new Date(b.node_time)
  )
  const truth = [...stamped].sort((a, b) => a.lamport - b.lamport)
  const wallDisagrees = [...stamped].sort((a, b) => new Date(a.node_time) - new Date(b.node_time))
    .some((e, i) => e.id !== truth[i].id)

  function pick(e) {
    setPicked((p) => (p.find((x) => x.id === e.id) ? p.filter((x) => x.id !== e.id) : [...p, e].slice(-2)))
  }
  const relation = picked.length === 2 ? compareVC(picked[0].vclock, picked[1].vclock) : null
  const relText = {
    before: 'A happened-before B (A → B): causally ordered',
    after: 'B happened-before A (B → A): causally ordered',
    concurrent: 'A ‖ B: CONCURRENT — neither could have influenced the other',
    equal: 'identical clocks',
  }

  return (
    <>
      <Concept
        unit="Unit 3" topic="Clock Synchronization · Lamport's Algorithm · Vector Algorithm"
        problem="Nodes have no shared clock. Wall clocks drift apart, so “which event came first?” cannot be answered by comparing timestamps."
      >
        Every node here has a deliberately wrong wall clock (±2 s). <b>Berkeley</b>: the leader acts as time daemon — it polls every node,
        compensates for round-trip delay, averages, and tells each node how much to adjust (no true time source needed).
        <b> Lamport</b> and <b>vector</b> clocks avoid wall time entirely: they ride on every gRPC call as metadata (added by a
        client/server <i>interceptor</i> in the middleware layer), and are stamped onto every event.
      </Concept>

      <section className="panel">
        <h2>Node clocks</h2>
        <table>
          <thead>
            <tr><th>Node</th><th>Wall clock</th><th>Skew vs real time</th><th>Lamport</th><th>Vector clock</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.node_id}>
                <td>{r.node_id}</td>
                {r.status === 'ONLINE' ? (
                  <>
                    <td className="mono">{fmtClock(r.physical_time)}</td>
                    <td className={Math.abs(r.skew_vs_real_ms) > 1000 ? 'bad-text' : ''}>{r.skew_vs_real_ms > 0 ? '+' : ''}{r.skew_vs_real_ms} ms</td>
                    <td>{r.lamport}</td>
                    <td className="mono small">{fmtVC(r.vclock)}</td>
                  </>
                ) : (<td colSpan={4} className="muted">offline</td>)}
              </tr>
            ))}
          </tbody>
        </table>
        <div style={{ display: 'flex', gap: 10, marginTop: 14, flexWrap: 'wrap' }}>
          <button onClick={async () => { await sync(); refresh() }} disabled={syncState.loading}>
            {syncState.loading ? 'Synchronising…' : 'Synchronise clocks (Berkeley)'}
          </button>
          <button className="secondary" onClick={async () => { await reskew(); refresh() }} disabled={reskewState.loading}>Re-skew clocks (reset demo)</button>
        </div>
        {syncState.data && syncState.data.success && (
          <>
            <Verdict good>{syncState.data.method} — {syncState.data.message}. All clocks now agree within a few ms.</Verdict>
            <table>
              <thead><tr><th>Node</th><th>Offset before</th><th>Adjustment</th><th>Offset after</th><th>Measured RTT</th></tr></thead>
              <tbody>
                {syncState.data.rows.map((r) => (
                  <tr key={r.node_id}>
                    <td>{r.node_id}</td><td>{r.offset_before_ms} ms</td><td>{r.adjustment_ms} ms</td>
                    <td>{r.offset_after_ms} ms</td><td>{r.rtt_ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
        {syncState.data && !syncState.data.success && <Verdict good={false}>{syncState.data.message}</Verdict>}
      </section>

      <section className="panel">
        <h2>Event ordering: wall clock vs Lamport clock</h2>
        <p className="muted">
          The latest events from all nodes. Sort them each way: the wall-clock order can put an effect before its cause
          (clocks are skewed); the Lamport order never does. Click two events to compare their vector clocks.
        </p>
        <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
          <button className={sortBy === 'lamport' ? '' : 'ghost'} onClick={() => setSortBy('lamport')}>Sort by Lamport (logical)</button>
          <button className={sortBy === 'wall' ? '' : 'ghost'} onClick={() => setSortBy('wall')}>Sort by node wall clock</button>
        </div>
        {sortBy === 'wall' && wallDisagrees && <Verdict good={false}>Wall-clock order disagrees with causal (Lamport) order — skewed clocks reorder events.</Verdict>}
        {sortBy === 'wall' && !wallDisagrees && stamped.length > 1 && <Verdict good>Orders happen to agree right now (clocks synchronised?). Press “Re-skew clocks” and generate more events.</Verdict>}
        <table>
          <thead><tr><th>#</th><th>Lamport</th><th>Node wall time</th><th>Source</th><th>Event</th><th>Vector clock</th></tr></thead>
          <tbody>
            {sorted.map((e, i) => (
              <tr key={e.id} onClick={() => pick(e)} className={picked.find((x) => x.id === e.id) ? 'picked' : 'clickable'}>
                <td>{i + 1}</td><td>{e.lamport}</td>
                <td className="mono">{new Date(e.node_time).toLocaleTimeString([], { hour12: false })}.{String(new Date(e.node_time).getMilliseconds()).padStart(3, '0')}</td>
                <td>{e.source}</td><td>{e.event}</td><td className="mono small">{fmtVC(e.vclock)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {stamped.length === 0 && <p className="muted">No stamped events yet — press Find Parking on the Overview tab.</p>}
        {relation && (
          <Verdict good={relation !== 'concurrent'}>
            A = {picked[0].event} @ {picked[0].source}, B = {picked[1].event} @ {picked[1].source}<br />{relText[relation]}
          </Verdict>
        )}
      </section>
    </>
  )
}
