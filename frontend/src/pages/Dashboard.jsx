import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiGet, apiPost } from "../api";
import ScrapeJobProgress from "../components/ScrapeJobProgress";

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [cancellingId, setCancellingId] = useState(null);
  const [error, setError] = useState("");

  const hasActiveJobs = jobs.some(
    (j) => j.status === "pending" || j.status === "running"
  );

  const load = () => {
    Promise.all([apiGet("/stats"), apiGet("/scrape-jobs")])
      .then(([s, j]) => {
        setStats(s);
        setJobs(j);
      })
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    load();
    const interval = setInterval(
      () => apiGet("/scrape-jobs").then(setJobs).catch(() => {}),
      hasActiveJobs ? 2000 : 15000
    );
    return () => clearInterval(interval);
  }, [hasActiveJobs]);

  useEffect(() => {
    if (!hasActiveJobs) return;
    const statsInterval = setInterval(
      () => apiGet("/stats").then(setStats).catch(() => {}),
      10000
    );
    return () => clearInterval(statsInterval);
  }, [hasActiveJobs]);

  const activeJobs = jobs.filter(
    (j) => j.status === "pending" || j.status === "running"
  );
  const recentJobs = jobs.slice(0, 5);

  const handleCancel = async (jobId) => {
    if (!window.confirm("Cancel this scrape job? Leads already found will be kept.")) {
      return;
    }
    setCancellingId(jobId);
    setError("");
    try {
      await apiPost(`/scrape-jobs/${jobId}/cancel`, {});
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setCancellingId(null);
    }
  };

  const handleCancelAll = async () => {
    if (!window.confirm("Cancel all active scrape jobs? Restart the API afterward.")) {
      return;
    }
    setError("");
    try {
      await apiPost("/scrape-jobs/cancel-all", {});
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <>
      <div className="page-header">
        <h1>Dashboard</h1>
        <p>Consulting-first lead pipeline for industrial & supply-chain operators.</p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {activeJobs.length > 0 && (
        <div className="card active-jobs-panel">
          <h3>
            <span className="live-dot" />
            Scrape in progress
          </h3>
          {activeJobs.map((job) => (
            <ScrapeJobProgress
              key={job.id}
              job={job}
              compact
              onCancel={handleCancel}
              cancelling={cancellingId === job.id}
            />
          ))}
          <button
            type="button"
            className="btn btn-danger btn-sm"
            style={{ marginBottom: "0.5rem" }}
            onClick={handleCancelAll}
          >
            Cancel all
          </button>
          <br />
          <Link to="/scrape" style={{ fontSize: "0.85rem" }}>
            View on Run Scrape →
          </Link>
        </div>
      )}

      {stats && (
        <div className="stats-grid">
          <div className="stat-card">
            <div className="label">Total Leads</div>
            <div className="value">{stats.total_leads}</div>
          </div>
          <div className="stat-card stat-hot">
            <div className="label">Hot (A-tier)</div>
            <div className="value">{stats.hot_leads ?? 0}</div>
          </div>
          <div className="stat-card">
            <div className="label">Qualified ({stats.thresholds?.qualified ?? 50}+)</div>
            <div className="value">{stats.qualified_leads}</div>
          </div>
          <div className="stat-card">
            <div className="label">With Email</div>
            <div className="value">{stats.with_email}</div>
          </div>
          <div className="stat-card">
            <div className="label">With Phone</div>
            <div className="value">{stats.with_phone}</div>
          </div>
          <div className="stat-card">
            <div className="label">Exported</div>
            <div className="value">{stats.exported}</div>
          </div>
        </div>
      )}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Recent Scrape Jobs</h3>
        {recentJobs.length === 0 ? (
          <p className="empty">
            No scrape jobs yet.{" "}
            <Link to="/scrape">Run your first scrape</Link>.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Industry</th>
                  <th>Location</th>
                  <th>Status</th>
                  <th>Leads</th>
                  <th>Message</th>
                </tr>
              </thead>
              <tbody>
                {recentJobs.map((j) => (
                  <tr key={j.id}>
                    <td>{j.industry}</td>
                    <td>
                      {[j.city, j.state].filter(Boolean).join(", ") || "—"}
                    </td>
                    <td>
                      <span className={`status-pill status-${j.status}`}>
                        {j.status}
                      </span>
                    </td>
                    <td>{j.companies_found}</td>
                    <td className="job-status">{j.progress_message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
