import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AppProvider } from './context'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import FindParking from './pages/FindParking'
import MyReservation from './pages/MyReservation'
import SystemMonitor from './pages/SystemMonitor'

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <div className="app-shell">
          <Sidebar />
          <div className="main">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/find" element={<FindParking />} />
              <Route path="/reservation" element={<MyReservation />} />
              <Route path="/monitor" element={<SystemMonitor />} />
            </Routes>
          </div>
        </div>
      </BrowserRouter>
    </AppProvider>
  )
}
