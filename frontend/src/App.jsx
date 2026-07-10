import { NavLink, Route, Routes } from "react-router-dom";
import { getEntityId } from "./api";
import { useAuth } from "./auth";
import Dashboard from "./pages/Dashboard";
import ScrapeJobs from "./pages/ScrapeJobs";
import LeadInbox from "./pages/LeadInbox";
import LeadDetail from "./pages/LeadDetail";
import Settings from "./pages/Settings";
import EmailCampaigns from "./pages/EmailCampaigns";
import Login from "./pages/Login";

function AppLayout() {
  const { user, brand, logout } = useAuth();
  const displayName = brand?.display_name || "Lead Generator";
  const productName = brand?.product_name || "Lead Generator";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">{displayName}</div>
        <div className="brand-title">{productName}</div>
        <nav>
          <NavLink to="/" end className="nav-link">
            Dashboard
          </NavLink>
          <NavLink to="/scrape" className="nav-link">
            Run Scrape
          </NavLink>
          <NavLink to="/leads" className="nav-link">
            Lead Inbox
          </NavLink>
          <NavLink to="/email" className="nav-link">
            Email Campaigns
          </NavLink>
          <NavLink to="/settings" className="nav-link">
            Settings
          </NavLink>
        </nav>
        {user && (
          <div className="sidebar-user">
            <div className="sidebar-user-name">{user.name}</div>
            <div className="sidebar-user-email">{user.email}</div>
            <button type="button" className="btn btn-secondary btn-sm" onClick={logout}>
              Sign out
            </button>
          </div>
        )}
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/scrape" element={<ScrapeJobs />} />
          <Route path="/leads" element={<LeadInbox />} />
          <Route path="/leads/:id" element={<LeadDetail />} />
          <Route path="/email" element={<EmailCampaigns />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  const { user, loading, authRequired } = useAuth();

  if (loading) {
    return <p className="empty login-loading">Loading...</p>;
  }

  if (authRequired) {
    const token = localStorage.getItem(`${getEntityId()}_token`);
    if (!token || !user?.id) {
      return <Login />;
    }
  }

  return <AppLayout />;
}
