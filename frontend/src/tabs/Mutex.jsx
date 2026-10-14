import { get, post } from '../api'
import { useAction, usePolling } from '../hooks'
import Concept, { Verdict } from '../components/Concept'

export default function Mutex() {
  const [lot, refreshLot] = usePolling(() => get('/api/overflow'), 2000)
  const [run, state] = useAction((useMutex) => post(`/api/demo/mutex?use_mutex=${useMutex}&capacity=2&hold_ms=300`))
  const d = state.data
  const bookings = Object.entries(lot?.bookings || {})

  return (
    <>
      <Concept
        unit="Unit 3" topic="Mutual Exclusion — Ricart-Agrawala · Lamport's Algorithm"
        problem="When every zone is full, cars go to one overflow lot shared by all three zones, and any zone can admit a car to it. Admitting is read → validate/pay → write. If two zones interleave, both read the same free count, both succeed and the lot is overbooked (a lost update)."
      >
        Ricart-Agrawala needs <b>no central lock server</b>: to enter the critical section a zone sends a REQUEST stamped with its
        <b> Lamport timestamp</b> to the other zones and enters only when all have replied. A zone replies immediately unless it is inside
        the critical section or wants it with an earlier (timestamp, id) — then it <b>defers</b> the reply until it leaves. 2(N−1) messages
        per entry. This is the one place the system needs a clock: the Lamport timestamp is what decides who goes first.
        The lot is deliberately a plain Redis counter with a non-atomic read-then-write, so the only thing preventing the race is the algorithm.
      </Concept>

      <section className="panel">
        <h2>The shared overflow lot</h2>
        {lot && !lot.error ? (
          <>
            <div className="card-grid">
              <div className="card"><div className="value">{lot.free ?? '—'} / {lot.capacity}</div><div className="label">Free slots</div></div>
              <div className="card"><div className="value">{bookings.length}</div><div className="label">Current overflow bookings</div></div>
            </div>
            {bookings.length > 0 && (
              <table>
                <thead><tr><th>Reservation</th><th>Admitted by</th></tr></thead>
                <tbody>
                  {bookings.map(([id, node]) => <tr key={id}><td className="mono">{id}</td><td>{node}</td></tr>)}
                </tbody>
              </table>
            )}
          </>
        ) : (
          <p className="muted">{lot?.error || 'Loading…'}</p>
        )}
        <p className="muted">
          Real bookings land here once all three zones are full (Find Parking returns zone OVERFLOW). The leader rotates which zone
          admits each one, so different zones can be competing for the lot at the same time.
        </p>
      </section>

      <section className="panel">
        <h2>Run the experiment — 3 zones admit a car at the same instant (capacity = 2)</h2>
        <p className="muted">Sets the lot to 2 free slots for the run, then resets it to empty at full capacity.</p>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button className="danger" onClick={async () => { await run(false); refreshLot() }} disabled={state.loading}>1. Run WITHOUT mutual exclusion</button>
          <button className="secondary" onClick={async () => { await run(true); refreshLot() }} disabled={state.loading}>2. Run WITH Ricart-Agrawala</button>
        </div>
        {state.loading && <p className="muted">Running…</p>}

        {d && !d.error && (
          <>
            {d.use_mutex ? (
              <Verdict good={!d.overbooked && !d.lost_update}>
                WITH Ricart-Agrawala: {d.accepted} of 3 bookings accepted for capacity {d.capacity}. Counter ended at {d.final_free_counter}
                (expected {d.expected_free_counter}). Critical sections {d.any_overlap ? 'OVERLAPPED' : 'never overlapped'}.
                Entry order: {d.entry_order.join(' → ')}.
              </Verdict>
            ) : (
              <Verdict good={!d.overbooked}>
                WITHOUT mutual exclusion: {d.accepted} of 3 bookings accepted for capacity {d.capacity} →
                {d.overbooked ? ' OVERBOOKED!' : ' no overbooking this time'} Counter ended at {d.final_free_counter} but should be {d.expected_free_counter}
                {d.lost_update ? ' — a lost update.' : '.'} Critical sections {d.any_overlap ? 'overlapped in time.' : 'did not overlap.'}
              </Verdict>
            )}

            <h3>Each zone's critical section</h3>
            <table>
              <thead><tr><th>Zone</th><th>REQUEST timestamp (Lamport)</th><th>Saw free slots</th><th>Outcome</th></tr></thead>
              <tbody>
                {d.results.map((r) => (
                  <tr key={r.node_id}>
                    <td>{r.node_id}</td>
                    <td>{r.error ? '—' : (r.request_ts || 'no request sent')}</td>
                    <td>{r.error ? '—' : r.saw_free}</td>
                    <td>
                      {r.error ? <span className="badge offline">{r.error}</span> : (
                        <><span className={`badge ${r.success ? 'online' : 'offline'}`}>{r.success ? 'BOOKED' : 'REJECTED'}</span> <span className="muted">{r.message}</span></>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {d.use_mutex && (
              <p className="muted">
                The zones enter in order of (Lamport timestamp, zone id): the smallest REQUEST goes first, the others defer to it.
              </p>
            )}

            <h3>Did the critical sections overlap?</h3>
            <table>
              <thead><tr><th>Pair</th><th>Real-time overlap</th></tr></thead>
              <tbody>
                {d.overlaps.map((o, i) => (
                  <tr key={i}>
                    <td>{o.a} vs {o.b}</td>
                    <td><span className={`badge ${o.overlap_ms > 0 ? 'offline' : 'online'}`}>{o.overlap_ms > 0 ? `${o.overlap_ms} ms (conflict!)` : 'none'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>

            {d.use_mutex && (
              <>
                <h3>Message trace (who deferred whom)</h3>
                <pre className="trace">{d.results.flatMap((r) => r.trace || []).join('\n')}</pre>
              </>
            )}
          </>
        )}
        {d && d.error && <Verdict good={false}>{d.error}</Verdict>}
      </section>
    </>
  )
}
