import { useApp } from '../context'
import StatusBadge from '../components/StatusBadge'

export default function Dashboard() {
  const { systemStatus } = useApp()
  const zones = systemStatus.zones || []

  const totals = zones.reduce(
    (acc, z) => ({
      total: acc.total + z.total_slots,
      available: acc.available + z.available_slots,
      occupied: acc.occupied + z.occupied_slots,
      reserved: acc.reserved + z.reserved_slots,
    }),
    { total: 0, available: 0, occupied: 0, reserved: 0 }
  )
  const onlineCount = zones.filter((z) => z.status === 'ONLINE').length

  return (
    <div>
      <h2>Dashboard</h2>
      <p className="muted">Live snapshot of the distributed parking network, pulled through the API Gateway.</p>

      <div className="card-grid">
        <div className="card"><div className="value">{totals.total}</div><div className="label">Total Slots</div></div>
        <div className="card"><div className="value">{totals.available}</div><div className="label">Available</div></div>
        <div className="card"><div className="value">{totals.occupied}</div><div className="label">Occupied</div></div>
        <div className="card"><div className="value">{totals.reserved}</div><div className="label">Reserved</div></div>
        <div className="card"><div className="value">{onlineCount} / {zones.length}</div><div className="label">Zones Online</div></div>
      </div>

      <div className="panel">
        <h3>Parking Zones</h3>
        <div className="card-grid">
          {zones.map((z) => (
            <div className="card" key={z.node_id}>
              <div className="zone-card-header">
                <strong>{z.zone_id}</strong>
                <StatusBadge status={z.status} />
              </div>
              <p className="muted">{z.node_id} · {z.host}:{z.port}</p>
              <table>
                <tbody>
                  <tr><td>Total</td><td>{z.total_slots}</td></tr>
                  <tr><td>Available</td><td>{z.available_slots}</td></tr>
                  <tr><td>Occupied</td><td>{z.occupied_slots}</td></tr>
                  <tr><td>Reserved</td><td>{z.reserved_slots}</td></tr>
                </tbody>
              </table>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
