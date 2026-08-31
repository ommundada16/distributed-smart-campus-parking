import { createContext, useContext, useEffect, useRef, useState } from 'react'
import { connectEventStream, getRecentEvents, getSystemStatus } from './api'

const AppContext = createContext(null)

const STATUS_TRIGGERING_EVENTS = new Set([
  'NODE_REGISTERED', 'NODE_FAILED', 'NODE_RECOVERED',
  'PARKING_RESERVED', 'PARKING_RELEASED', 'SLOT_STATUS_CHANGED',
])

export function AppProvider({ children }) {
  const [events, setEvents] = useState([])
  const [systemStatus, setSystemStatus] = useState({ services: [], zones: [] })
  const [reservation, setReservationState] = useState(() => {
    const saved = localStorage.getItem('activeReservation')
    return saved ? JSON.parse(saved) : null
  })

  const socketRef = useRef(null)

  function setReservation(value) {
    setReservationState(value)
    if (value) localStorage.setItem('activeReservation', JSON.stringify(value))
    else localStorage.removeItem('activeReservation')
  }

  async function refreshStatus() {
    try {
      const data = await getSystemStatus()
      setSystemStatus(data)
    } catch {
      // gateway unreachable — leave last-known status on screen
    }
  }

  useEffect(() => {
    refreshStatus()
    getRecentEvents(20).then((data) => setEvents(data.events || []))

    const socket = connectEventStream((event) => {
      setEvents((prev) => [event, ...prev].slice(0, 100))
      if (STATUS_TRIGGERING_EVENTS.has(event.event)) {
        refreshStatus()
      }
    })
    socketRef.current = socket

    const pollId = setInterval(refreshStatus, 5000)

    return () => {
      socket.close()
      clearInterval(pollId)
    }
  }, [])

  return (
    <AppContext.Provider value={{ events, systemStatus, refreshStatus, reservation, setReservation }}>
      {children}
    </AppContext.Provider>
  )
}

export function useApp() {
  return useContext(AppContext)
}
