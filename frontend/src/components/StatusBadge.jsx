export default function StatusBadge({ status }) {
  const cls = (status || '').toLowerCase()
  return <span className={`badge ${cls}`}>{status}</span>
}
