// Thin wrapper around the API Gateway's HTTP + WebSocket endpoints.
// The frontend never talks to the coordinator or zones directly — the
// gateway is the single entry point, same as the architecture diagram.

export async function getSystemStatus() {
  const res = await fetch('/api/system/status')
  return res.json()
}

export async function findParking() {
  const res = await fetch('/api/parking/find', { method: 'POST' })
  return res.json()
}

export async function releaseParking(reservationId) {
  const res = await fetch('/api/parking/release', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reservation_id: reservationId }),
  })
  return res.json()
}

export async function getRecentEvents(count = 20) {
  const res = await fetch(`/api/events/recent?count=${count}`)
  return res.json()
}

export async function setZoneFailure(zoneKey, simulateFailure) {
  const res = await fetch(`/api/admin/zone/${zoneKey}/failure`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ simulate_failure: simulateFailure }),
  })
  return res.json()
}

export function connectEventStream(onEvent) {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws`)
  socket.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data))
    } catch {
      // ignore malformed frames
    }
  }
  return socket
}
