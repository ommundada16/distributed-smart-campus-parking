import { NavLink } from 'react-router-dom'

export default function Sidebar() {
  return (
    <div className="sidebar">
      <h1>Distributed Smart<br />Campus Parking</h1>
      <nav>
        <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}>Dashboard</NavLink>
        <NavLink to="/find" className={({ isActive }) => (isActive ? 'active' : '')}>Find Parking</NavLink>
        <NavLink to="/reservation" className={({ isActive }) => (isActive ? 'active' : '')}>My Reservation</NavLink>
        <NavLink to="/monitor" className={({ isActive }) => (isActive ? 'active' : '')}>System Monitor</NavLink>
      </nav>
    </div>
  )
}
