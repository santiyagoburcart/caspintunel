import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './lib/auth'
import { Spinner } from './components/ui'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Users from './pages/Users'
import Plans from './pages/Plans'
import Payments from './pages/Payments'
import Accounting from './pages/Accounting'
import Cards from './pages/Cards'
import Monitoring from './pages/Monitoring'
import Branding from './pages/Branding'
import { Pages, Roles, Themes } from './pages/Simple'

function Private({ children }) {
  const { staff, loading } = useAuth()
  if (loading) return <div className="grid min-h-full place-items-center"><Spinner /></div>
  return staff ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Private><Layout /></Private>}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/users" element={<Users />} />
        <Route path="/plans" element={<Plans />} />
        <Route path="/payments" element={<Payments />} />
        <Route path="/accounting" element={<Accounting />} />
        <Route path="/cards" element={<Cards />} />
        <Route path="/monitoring" element={<Monitoring />} />
        <Route path="/branding" element={<Branding />} />
        <Route path="/pages" element={<Pages />} />
        <Route path="/themes" element={<Themes />} />
        <Route path="/roles" element={<Roles />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
