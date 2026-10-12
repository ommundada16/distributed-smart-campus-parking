import { useState } from 'react'
import { get, post } from '../api'
import { useAction, usePolling } from '../hooks'
import Concept, { Verdict } from '../components/Concept'

export default function Snapshot() {
  const [flex, refresh] = usePolling(() => get('/api/flex'), 1500)
  const [amount, setAmount] = useState(3)
  const [delay, setDelay] = useState(3000)
  const [run, state] = useAction(() => post(`/api/demo/snapshot?amount=${amount}&delay_ms=${delay}`))
  const d = state.data

  return (
    <>
      <Concept
        unit="Unit 3" topic="Global State — Chandy-Lamport snapshot"
        problem="Zones lend each other flexible bays. Total bays across the campus is constant (30), but while a transfer is in flight the bays are on neither zone: adding up the zones' local counts gives the wrong total."
      >
        Chandy-Lamport records a <b>consistent global state without stopping the system</b>. The initiator records its own state and sends a
        MARKER on every outgoing channel. A node receiving its first marker records its state and forwards markers; it then records every
        message arriving on a channel until that channel's marker arrives — those are the messages <i>in flight</i>. Channels are FIFO
        (each is a queue drained by one sender thread), which the algorithm requires.
      </Concept>

      <section className="panel">
        <h2>Flexible bays per zone (the conserved quantity)</h2>
        <div className="card-grid">
          {(flex?.zones || []).map((z) => (
            <div className="card" key={z.node_id}><div className="value">{z.flex_bays ?? '—'}</div><div className="label">{z.node_id}</div></div>
          ))}
          <div className="card"><div className="value">{flex?.total ?? '—'}</div><div className="label">Sum of local counts</div></div>
        </div>

        <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
          <label>Bays to move <input type="number" min="1" max="9" value={amount} onChange={(e) => setAmount(+e.target.value)} /></label>
          <label>Network delay (ms) <input type="number" min="500" max="8000" step="500" value={delay} onChange={(e) => setDelay(+e.target.value)} /></label>
          <button onClick={async () => { await run(); refresh() }} disabled={state.loading}>
            {state.loading ? 'Snapshotting… (waits for the transfer)' : 'Transfer bays and take a snapshot mid-flight'}
          </button>
        </div>
        <p className="muted">The richest zone sends bays to the poorest; 0.4 s later ZONE_A starts a snapshot while the transfer is still on the wire.</p>

        {d && !d.success && <Verdict good={false}>{d.message}</Verdict>}
        {d && d.success && (
          <>
            <Verdict good={d.consistent}>
              Snapshot {d.snapshot_id} (initiated by {d.initiator}) is {d.consistent ? 'CONSISTENT' : 'inconsistent'}:
              recorded node states {d.recorded_total} + in-flight on channels {d.in_flight_total} = <b>{d.snapshot_total}</b>
              {' '}(expected {d.expected_total}).
            </Verdict>
            <Verdict good={false}>
              Naive approach — just reading each zone's counter during the transfer ({Object.entries(d.naive_reading).map(([k, v]) => `${k.replace('ZONE_', '')}=${v}`).join(', ')})
              gives <b>{d.naive_total}</b>: {d.expected_total - d.naive_total} bays have “vanished” because they are in the network.
            </Verdict>
            <p>Transfer: <b>{d.transfer.amount}</b> bays {d.transfer.from} → {d.transfer.to}, delayed {d.transfer.delay_ms} ms.</p>
            <table>
              <thead><tr><th>Node</th><th>Recorded local state</th><th>Recorded incoming channels (in-flight messages)</th></tr></thead>
              <tbody>
                {d.nodes.map((n) => (
                  <tr key={n.node_id}>
                    <td>{n.node_id}</td><td>{n.recorded_flex} bays</td>
                    <td>
                      {(n.channels || []).map((c) => (
                        <span key={c.from} style={{ marginRight: 14 }}>
                          {c.from} → {c.to}: {c.in_flight.length ? <b className="bad-text">[{c.in_flight.join(', ')}] in flight</b> : 'empty'}
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>
    </>
  )
}
