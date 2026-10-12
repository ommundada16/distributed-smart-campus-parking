// A short "why this exists" box that ties each demo back to the syllabus unit
// and the distributed-systems problem it solves.

export default function Concept({ unit, topic, problem, children }) {
  return (
    <div className="concept">
      <div className="concept-head">
        <span className="unit-tag">{unit}</span>
        <strong>{topic}</strong>
      </div>
      {problem && (
        <p className="concept-problem">
          <b>Problem:</b> {problem}
        </p>
      )}
      <div className="concept-body">{children}</div>
    </div>
  )
}

export function Verdict({ good, children }) {
  return <div className={`verdict ${good ? 'good' : 'bad'}`}>{children}</div>
}

export function Bar({ value, max, label, color }) {
  const pct = max > 0 ? Math.min(100, (100 * value) / max) : 0
  return (
    <div className="bar-row">
      <span className="bar-label">{label}</span>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${pct}%`, background: color || 'var(--primary)' }} />
      </div>
      <span className="bar-value">{value}</span>
    </div>
  )
}
