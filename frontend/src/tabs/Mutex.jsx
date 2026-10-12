import { post } from '../api'
import { fmtVC, useAction } from '../hooks'
import Concept, { Verdict } from '../components/Concept'

export default function Mutex() {
  const [run, state] = useAction((useMutex) => post(`/api/demo/mutex?use_mutex=${useMutex}&capacity=2&hold_ms=300`))
  const d = state.data

  return (
    <>
      <Concept
        unit="Unit 3" topic="Mutual Exclusion — Ricart-Agrawala"
        problem="Three zones sell slots from one shared overflow lot with 2 slots left. Each does read → validate/pay → write. If they interleave, all three read “2 free”, all succeed and the lot is overbooked (a lost update)."
      >
        Ricart-Agrawala needs <b>no central lock server</b>: to enter the critical section a zone multicasts a REQUEST stamped with its
        Lamport time to the other zones and enters only when all have replied. A zone replies immediately unless it is inside the
        critical section or wants it with an earlier (timestamp, id) — then it <b>defers</b> the reply until it leaves. 2(N−1) messages per entry.
        The shared lot is deliberately a plain Redis counter with a non-atomic read-then-write, so the only thing preventing the race is the algorithm.
      </Concept>

      <section className="panel">
        <h2>Run the experiment — 3 zones book at the same instant (capacity = 2)</h2>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button className="danger" onClick={() => run(false)} disabled={state.loading}>1. Run WITHOUT mutual exclusion</button>
          <button className="secondary" onClick={() => run(true)} disabled={state.loading}>2. Run WITH Ricart-Agrawala</button>
        </div>
        {state.loading && <p className="muted">Running…</p>}

        {d && !d.error && (
          <>
            {d.use_mutex ? (
              <Verdict good={!d.overbooked && !d.lost_update}>
                WITH Ricart-Agrawala: {d.accepted} of 3 bookings accepted for capacity {d.capacity}. Counter ended at {d.final_free_counter}
                (expected {d.expected_free_counter}). Critical sections {d.any_overlap ? 'OVERLAPPED' : 'never overlapped'}.
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
              <thead><tr><th>Zone</th><th>Saw free slots</th><th>Outcome</th><th>Lamport at entry</th><th>Vector clock at entry</th></tr></thead>
              <tbody>
                {d.results.map((r) => (
                  <tr key={r.node_id}>
                    <td>{r.node_id}</td><td>{r.saw_free}</td>
                    <td><span className={`badge ${r.success ? 'online' : 'offline'}`}>{r.success ? 'BOOKED' : 'REJECTED'}</span> <span className="muted">{r.message}</span></td>
                    <td>{r.lamport}</td><td className="mono small">{fmtVC(r.vclock)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <h3>Causality between the zones' entries (vector clocks)</h3>
            <table>
              <thead><tr><th>Pair</th><th>Relation</th><th>Real-time overlap</th></tr></thead>
              <tbody>
                {d.relations.map((r, i) => (
                  <tr key={i}>
                    <td>{r.a} vs {r.b}</td>
                    <td><span className={`badge ${r.relation === 'concurrent' ? 'offline' : 'online'}`}>{r.relation === 'concurrent' ? 'CONCURRENT (conflict!)' : `${r.relation} (ordered)`}</span></td>
                    <td>{r.overlap_ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted">
              Without the algorithm the zones never communicate, so their entries are concurrent — the conflict is detectable but
              unavoidable. With it, the REQUEST/REPLY messages create a happened-before chain, so every pair is totally ordered.
            </p>

            {d.use_mutex && (
              <>
                <h3>Message trace (who deferred whom)</h3>
                <pre className="trace">{d.results.flatMap((r) => r.trace).join('\n')}</pre>
              </>
            )}
          </>
        )}
        {d && d.error && <Verdict good={false}>{d.error}</Verdict>}
      </section>
    </>
  )
}
