function formatTime(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  return date.toLocaleTimeString()
}

export default function EventLog({ events, limit = 20 }) {
  const rows = events.slice(0, limit)
  if (rows.length === 0) {
    return <p className="muted">No events yet — trigger a parking request to see activity.</p>
  }
  return (
    <div className="event-log">
      {rows.map((e) => (
        <div className="event-row" key={e.id}>
          <span className="comm-tag message">MESSAGE</span>
          <span className="event-type">{e.event}</span>
          <span className="event-time">{formatTime(e.timestamp)}</span>
          <span className="muted">source: {e.source}</span>
        </div>
      ))}
    </div>
  )
}
