import { useState } from 'react'
import { findParking } from '../api'
import { useApp } from '../context'

export default function FindParking() {
  const { setReservation, refreshStatus } = useApp()
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  async function handleFind() {
    setLoading(true)
    setResult(null)
    try {
      const data = await findParking()
      setResult(data)
      if (data.success) {
        setReservation({
          zone_id: data.zone_id,
          node_id: data.node_id,
          slot_id: data.slot_id,
          reservation_id: data.reservation_id,
        })
        refreshStatus()
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2>Find Parking</h2>
      <p className="muted">
        Request routes: Frontend → API Gateway → Coordinator → gRPC → a Parking Zone → back.
      </p>

      <div className="panel">
        <button onClick={handleFind} disabled={loading}>
          {loading ? 'Searching...' : 'Find Parking'}
        </button>

        {result && result.success && (
          <div style={{ marginTop: 20 }}>
            <table>
              <tbody>
                <tr><td>Recommended Zone</td><td>{result.zone_id}</td></tr>
                <tr><td>Slot ID</td><td>{result.slot_id}</td></tr>
                <tr><td>Reservation ID</td><td>{result.reservation_id}</td></tr>
              </tbody>
            </table>
            <p className="muted" style={{ marginTop: 12 }}>
              Saved as your active reservation — see the "My Reservation" page to release it.
            </p>
          </div>
        )}

        {result && !result.success && (
          <p style={{ color: 'var(--red)', marginTop: 16 }}>{result.message}</p>
        )}
      </div>
    </div>
  )
}
