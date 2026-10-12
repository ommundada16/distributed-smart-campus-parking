// Thin wrapper around the API Gateway's HTTP + WebSocket endpoints.
// The frontend never talks to the coordinators or zones directly — the
// gateway is the single entry point (behind the Nginx load balancer in Docker).

export async function call(path, { method = 'GET', body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json()
  return {
    data,
    servedBy: res.headers.get('X-Served-By'),
    cache: res.headers.get('X-Cache-Status'),
    upstream: res.headers.get('X-Upstream'),
  }
}

export const get = (path) => call(path).then((r) => r.data)
export const post = (path, body) => call(path, { method: 'POST', body }).then((r) => r.data)

// ---- FA-1 calls (kept) ----
export const getSystemStatus = () => get('/api/system/status')
export const findParking = (policy = '') => post(`/api/parking/find${policy ? `?policy=${policy}` : ''}`)
export const releaseParking = (reservationId) => post('/api/parking/release', { reservation_id: reservationId })
export const getRecentEvents = (count = 40) => get(`/api/events/recent?count=${count}`)
export const setZoneFailure = (zoneKey, simulateFailure) =>
  post(`/api/admin/zone/${zoneKey}/failure`, { simulate_failure: simulateFailure })

// ---- FA-2 calls ----
export const setCoordinatorFailure = (id, simulateFailure) =>
  post(`/api/admin/coordinator/${id}/failure`, { simulate_failure: simulateFailure })

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
