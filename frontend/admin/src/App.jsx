import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './lib/auth'
import { Spinner } from './components/ui'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Users from './pages/Users'
import UserOrders from './pages/UserOrders'
import DeletedUsers from './pages/DeletedUsers'
import Plans from './pages/Plans'
import Payments from './pages/Payments'
import Transactions from './pages/Transactions'
import TransactionDetail from './pages/TransactionDetail'
import Accounting from './pages/Accounting'
import Cards from './pages/Cards'
import Monitoring from './pages/Monitoring'
import Services from './pages/Services'
import ServiceEdit from './pages/ServiceEdit'
import Branding from './pages/Branding'
import Settings from './pages/Settings'
import Notifications from './pages/Notifications'
import Apps from './pages/Apps'
import { PanelConnection, Bots } from './pages/Integrations'
import EmailSettings from './pages/EmailSettings'
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
        <Route path="/users/deleted" element={<DeletedUsers />} />
        <Route path="/users/deleted/:id" element={<DeletedUsers />} />
        <Route path="/users/:id/orders" element={<UserOrders />} />
        <Route path="/plans" element={<Plans />} />
        <Route path="/payments" element={<Payments />} />
        <Route path="/payments/:id" element={<TransactionDetail />} />
        <Route path="/transactions" element={<Transactions />} />
        <Route path="/transactions/:id" element={<TransactionDetail />} />
        <Route path="/accounting" element={<Accounting />} />
        <Route path="/cards" element={<Cards />} />
        <Route path="/monitoring" element={<Monitoring />} />
        <Route path="/services" element={<Services />} />
        <Route path="/services/:id" element={<ServiceEdit />} />
        <Route path="/panel-link" element={<PanelConnection />} />
        <Route path="/bots" element={<Bots />} />
        <Route path="/branding" element={<Branding />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/settings/email" element={<EmailSettings />} />
        <Route path="/settings/:section" element={<Settings />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/apps" element={<Apps />} />
        <Route path="/pages" element={<Pages />} />
        <Route path="/themes" element={<Themes />} />
        <Route path="/roles" element={<Roles />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
