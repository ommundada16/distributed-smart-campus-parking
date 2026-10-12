import { useState } from 'react'
import { get, post, findParking, releaseParking } from '../api'
import { useAction, usePolling } from '../hooks'
import Concept, { Verdict } from '../components/Concept'

export default function Ledger() {
  const [ledger, refresh] = usePolling(() => get('/api/ledger?limit=14'), 2000)
  const [zone, setZone] = useState('B')
  const [tamper, tState] = useAction(() => post(`/api/ledger/tamper?zone=${zone}`))
  const [repair, rState] = useAction(() => post(`/api/ledger/repair?zone=${zone}`))
  const [book, bState] = useAction(async () => {
    const r = await findParking()
    if (r.success) await releaseParking(r.reservation_id)
    return r
  })

  const replicas = ledger?.replicas || []
  const blocks = [...(ledger?.blocks || [])].reverse()

  return (
    <>
      <Concept
        unit="Unit 4 (self-study)" topic="Blockchain & distributed ledger technologies — trade-offs"
        problem="Every booking must be an auditable record that no single zone (or admin) can quietly rewrite."
      >
        Each booking is a <b>block</b>: its hash covers the previous block's hash, so changing any old block breaks every link after it.
        The coordinator leader proposes each block to <b>all three zones</b>; it commits when a <b>majority (2 of 3)</b> accept — so one
        zone being down doesn't stop bookings (availability), and the zone <b>catches up from its peers</b> when it returns (eventual consistency).
        This is a permissioned, single-leader ledger — no proof-of-work — which trades Byzantine fault tolerance for speed and simplicity.
      </Concept>

      <section className="panel">
        <h2>Replicas</h2>
        <Verdict good={!!ledger?.consistent}>
          {ledger?.consistent ? 'All online replicas hold the identical, valid chain.' : 'Replicas DISAGREE or one failed verification — see below.'}
        </Verdict>
        <table>
          <thead><tr><th>Replica</th><th>Status</th><th>Blocks</th><th>Chain valid?</th><th>Head hash</th></tr></thead>
          <tbody>
            {replicas.map((r) => (
              <tr key={r.node_id}>
                <td>{r.node_id}</td>
                <td><span className={`badge ${r.status === 'ONLINE' ? 'online' : 'offline'}`}>{r.status}</span></td>
                <td>{r.length ?? '—'}</td>
                <td>{r.status !== 'ONLINE' ? '—' : r.valid
                  ? <span className="badge online">VALID</span>
                  : <span className="badge offline">BROKEN at block #{r.bad_index}</span>}</td>
                <td className="mono small">{r.head_hash ? r.head_hash.slice(0, 16) + '…' : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div style={{ display: 'flex', gap: 10, marginTop: 14, flexWrap: 'wrap', alignItems: 'center' }}>
          <button onClick={async () => { await book(); refresh() }} disabled={bState.loading}>Create a booking (adds 2 blocks)</button>
          <span className="muted">Attack zone:</span>
          <select value={zone} onChange={(e) => setZone(e.target.value)}>
            <option>A</option><option>B</option><option>C</option>
          </select>
          <button className="danger" onClick={async () => { await tamper(); refresh() }} disabled={tState.loading}>Tamper with a block</button>
          <button className="secondary" onClick={async () => { await repair(); refresh() }} disabled={rState.loading}>Repair from peers</button>
        </div>
        {tState.data && <p className="muted">{tState.data.success ? `Zone ${zone}: block #${tState.data.index} silently rewritten (its stored hash was not updated).` : tState.data.message}</p>}
        {rState.data && <p className="muted">{rState.data.message}</p>}
      </section>

      <section className="panel">
        <h2>Latest blocks (from the longest valid replica)</h2>
        <table>
          <thead><tr><th>#</th><th>Transaction</th><th>Zone / slot</th><th>Lamport</th><th>Hash</th><th>Prev hash</th></tr></thead>
          <tbody>
            {blocks.map((b) => (
              <tr key={b.index}>
                <td>{b.index}</td>
                <td><span className={`badge ${b.tx.type === 'RESERVE' ? 'reserved' : 'available'}`}>{b.tx.type}</span></td>
                <td>{b.tx.zone_id ? `${b.tx.zone_id} · ${b.tx.slot_id}` : b.tx.note || '—'}</td>
                <td>{b.lamport}</td>
                <td className="mono small">{b.hash.slice(0, 14)}…</td>
                <td className="mono small">{b.prev_hash.slice(0, 14)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  )
}
