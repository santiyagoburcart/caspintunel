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
import SmsLog from './pages/SmsLog'
import Docs from './pages/Docs'
import PathsSettings from './pages/PathsSettings'
import { AgencyAdminDetail, AgencyAdminNew, AgencyAdmins, AgencyDashboard, AgencyGroups, AgencyLedger, AgencySettings, AgencySyncLogs } from './pages/Agency'
import Accounting from './pages/Accounting'
import Tickets from './pages/Tickets'
import TicketTopics from './pages/TicketTopics'
import { CrmCase, CrmLeads, CrmQueue, CrmReports, CrmSettings, Customer360 } from './pages/Crm'
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
        <Route path="/sms-log" element={<SmsLog />} />
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
        <Route path="/settings/paths" element={<PathsSettings />} />
        <Route path="/settings/:section" element={<Settings />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/apps" element={<Apps />} />
        <Route path="/pages" element={<Pages />} />
        <Route path="/themes" element={<Themes />} />
        <Route path="/roles" element={<Roles />} />
        <Route path="/agency" element={<AgencyDashboard />} />
        <Route path="/agency/admins" element={<AgencyAdmins />} />
        <Route path="/agency/admins/new" element={<AgencyAdminNew />} />
        <Route path="/agency/admins/:username" element={<AgencyAdminDetail />} />
        <Route path="/agency/admins/:username/:tab" element={<AgencyAdminDetail />} />
        <Route path="/agency/groups" element={<AgencyGroups />} />
        <Route path="/agency/ledger" element={<AgencyLedger />} />
        <Route path="/agency/sync-logs" element={<AgencySyncLogs />} />
        <Route path="/agency/settings" element={<AgencySettings />} />
        <Route path="/tickets" element={<Tickets />} />
        <Route path="/tickets/topics" element={<TicketTopics />} />
        <Route path="/tickets/:id" element={<Tickets />} />
        <Route path="/crm" element={<CrmQueue />} />
        <Route path="/crm/cases/:id" element={<CrmCase />} />
        <Route path="/crm/customers/:id" element={<Customer360 />} />
        <Route path="/crm/leads" element={<CrmLeads />} />
        <Route path="/crm/reports" element={<CrmReports />} />
        <Route path="/crm/settings" element={<CrmSettings />} />
        <Route path="/docs" element={<Docs />} />
        <Route path="/docs/:slug" element={<Docs />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
