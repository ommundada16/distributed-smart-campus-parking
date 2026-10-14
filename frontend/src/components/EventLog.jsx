// Renders every event exactly as it arrived off the Redis Streams -> WebSocket
// pipeline, tagged by which mechanism produced it. Events published by the
// coordinators and zones also carry a Lamport timestamp (L).

function formatTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString()
}

const GROUPS = {
  ELECTION: ['LEADER_ELECTED', 'LEADER_LOST'],
  MUTEX: ['OVERFLOW_BOOKED', 'OVERFLOW_REJECTED', 'OVERFLOW_RELEASED'],
  LEDGER: ['LEDGER_COMMITTED', 'LEDGER_COMMIT_FAILED', 'LEDGER_TAMPERED', 'LEDGER_REPAIRED'],
  BALANCE: ['POLICY_CHANGED'],
}

function groupOf(event) {
  return Object.keys(GROUPS).find((g) => GROUPS[g].includes(event)) || null
}

function describe(e) {
  if (e.event === 'RPC_CALL') {
    return { tag: 'RPC', cls: 'rpc', text: `${e.source} → ${e.data.target} → ${e.data.method}  (${e.data.result})` }
  }
  if (e.event === 'P2P_MESSAGE') {
    return { tag: 'P2P', cls: 'p2p', text: `${e.source} → ${e.data.peer} → ${e.data.request}  (${e.data.reply})` }
  }
  const group = groupOf(e.event)
  if (group) {
    const detail = Object.entries(e.data || {}).map(([k, v]) => `${k}=${v}`).join(' ')
    return { tag: group, cls: group.toLowerCase(), text: `${e.event}  ${detail}  (${e.source})` }
  }
  return { tag: 'MESSAGE', cls: 'message', text: `${e.event}  (source: ${e.source})` }
}

export default function EventLog({ events, limit = 30, showClocks = false, filter }) {
  const rows = (filter ? events.filter(filter) : events).slice(0, limit)
  if (rows.length === 0) {
    return <p className="muted">No activity yet — use the buttons on this page to generate some.</p>
  }
  return (
    <div className="event-log">
      {rows.map((e) => {
        const { tag, cls, text } = describe(e)
        return (
          <div className="event-row" key={e.id}>
            <span className={`comm-tag ${cls}`}>{tag}</span>
            <span className="event-type">{text}</span>
            {showClocks && e.lamport != null && (
              <span className="event-clock">L={e.lamport}</span>
            )}
            <span className="event-time">{formatTime(e.timestamp)}</span>
          </div>
        )
      })}
    </div>
  )
}
