// Renders every event exactly as it arrived off the Redis Streams -> WebSocket
// pipeline, but tags it by which communication style produced it, so a single
// feed on screen tells the whole story: RPC, P2P, and message-bus activity
// side by side.

function formatTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString()
}

function describe(e) {
  if (e.event === 'RPC_CALL') {
    return { tag: 'RPC', cls: 'rpc', text: `${e.source} → ${e.data.target} → ${e.data.method}  (${e.data.result})` }
  }
  if (e.event === 'P2P_MESSAGE') {
    return { tag: 'P2P', cls: 'p2p', text: `${e.source} → ${e.data.peer} → ${e.data.request}  (${e.data.reply})` }
  }
  return { tag: 'MESSAGE', cls: 'message', text: `${e.event}  (source: ${e.source})` }
}

export default function EventLog({ events, limit = 30 }) {
  const rows = events.slice(0, limit)
  if (rows.length === 0) {
    return <p className="muted">No activity yet — click "Find Parking" below to generate some.</p>
  }
  return (
    <div className="event-log">
      {rows.map((e) => {
        const { tag, cls, text } = describe(e)
        return (
          <div className="event-row" key={e.id}>
            <span className={`comm-tag ${cls}`}>{tag}</span>
            <span className="event-type">{text}</span>
            <span className="event-time">{formatTime(e.timestamp)}</span>
          </div>
        )
      })}
    </div>
  )
}
