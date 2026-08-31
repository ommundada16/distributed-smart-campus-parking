import { useState } from 'react'
import { Link } from 'react-router-dom'
import { releaseParking } from '../api'
import { useApp } from '../context'

export default function MyReservation() {
  const { reservation, setReservation, refreshStatus } = useApp()
  const [message, setMessage] = useState(null)
  const [loading, setLoading] = useState(false)

  async function handleRelease() {
    setLoading(true)
    try {
      const data = await releaseParking(reservation.reservation_id)
      if (data.success) {
        setReservation(null)
        setMessage('Reservation released.')
        refreshStatus()
      } else {
        setMessage(data.message)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2>My Reservation</h2>

      {!reservation && (
        <div className="panel">
          <p>You don't have an active reservation.</p>
          <Link to="/find"><button>Find Parking</button></Link>
        </div>
      )}

      {reservation && (
        <div className="reservation-box">
          <h3>{reservation.zone_id}</h3>
          <p style={{ fontSize: 22, fontWeight: 700 }}>{reservation.slot_id}</p>
          <p className="muted">Reservation ID: {reservation.reservation_id}</p>
          <button className="danger" onClick={handleRelease} disabled={loading} style={{ marginTop: 16 }}>
            {loading ? 'Releasing...' : 'Release Slot'}
          </button>
        </div>
      )}

      {message && <p className="muted" style={{ marginTop: 16 }}>{message}</p>}
    </div>
  )
}
