import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api";
import ScrapeJobProgress from "../components/ScrapeJobProgress";
import { parseScrapeProgress } from "../utils/scrapeProgress";

export default function ScrapeJobs() {
  const [config, setConfig] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [form, setForm] = useState({
    industry: "manufacturing",
    city: "",
    state: "",
    keyword_override: "",
    positive_keywords_override: "",
    negative_keywords_override: "",
    enrichment_mode: "quality",
  });
  const [loading, setLoading] = useState(false);
  const [cancellingId, setCancellingId] = useState(null);
  const [error, setError] = useState("");

  const loadJobs = () => {
    apiGet("/scrape-jobs")
      .then(setJobs)
      .catch((e) => setError(e.message));
  };

  const load = () => {
    if (!config) {
      apiGet("/config").then(setConfig).catch((e) => setError(e.message));
    }
    loadJobs();
  };

  const hasActiveJobs = jobs.some(
    (j) => j.status === "pending" || j.status === "running"
  );

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const interval = setInterval(loadJobs, hasActiveJobs ? 2000 : 15000);
    return () => clearInterval(interval);
  }, [hasActiveJobs]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await apiPost("/scrape-jobs", {
        industry: form.industry,
        city: form.city || null,
        state: form.state || null,
        keyword_override: form.keyword_override || null,
        positive_keywords_override: form.positive_keywords_override || null,
        negative_keywords_override: form.negative_keywords_override || null,
        enrichment_mode: form.enrichment_mode,
      });
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fillMetro = (metro) => {
    setForm((f) => ({ ...f, city: metro.city, state: metro.state }));
  };

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
    if (
      !window.confirm(
        "Cancel ALL active scrape jobs? You must restart the API afterward to kill stuck background processes."
      )
    ) {
      return;
    }
    setError("");
    try {
      const result = await apiPost("/scrape-jobs/cancel-all", {});
      loadJobs();
      setError("");
      alert(result.message || `Cancelled ${result.cancelled_count} job(s). Restart the API (run_dev.ps1) before starting a new scrape.`);
    } catch (err) {
      setError(err.message);
    }
  };

  const activeJobs = jobs.filter(
    (j) => j.status === "pending" || j.status === "running"
  );
  const recentJobs = jobs.filter(
    (j) => j.status === "completed" || j.status === "failed" || j.status === "cancelled"
  );

  return (
    <>
      <div className="page-header">
        <h1>Run Scrape</h1>
        <p>Discover companies via public web search, enrich, and score against ICP.</p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {activeJobs.length > 0 && (
        <div className="card active-jobs-panel">
          <h3>
            <span className="live-dot" />
            Active Jobs ({activeJobs.length})
          </h3>
          <p style={{ color: "var(--muted)", fontSize: "0.9rem", marginTop: 0 }}>
            Updates every 2 seconds. Typical runtime: 5–15 minutes for ~25 companies.
            If jobs look stuck over 20 minutes, cancel all and restart the API.
          </p>
          <div style={{ marginBottom: "0.75rem" }}>
            <button
              type="button"
              className="btn btn-danger btn-sm"
              onClick={handleCancelAll}
            >
              Cancel all stuck jobs
            </button>
          </div>
          {activeJobs.map((job) => (
            <ScrapeJobProgress
              key={job.id}
              job={job}
              onCancel={handleCancel}
              cancelling={cancellingId === job.id}
            />
          ))}
        </div>
      )}

      <div className="card">
        <form onSubmit={handleSubmit}>
          <div className="form-row">
            <div>
              <label>Industry</label>
              <select
                value={form.industry}
                onChange={(e) => setForm({ ...form, industry: e.target.value })}
              >
                {config?.industries?.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label>City (optional)</label>
              <input
                value={form.city}
                onChange={(e) => setForm({ ...form, city: e.target.value })}
                placeholder="Houston"
              />
            </div>
            <div>
              <label>State (optional)</label>
              <input
                value={form.state}
                onChange={(e) => setForm({ ...form, state: e.target.value })}
                placeholder="TX"
                maxLength={2}
              />
            </div>
          </div>
          <div className="form-row">
            <div>
              <label>Search keyword override (optional)</label>
              <input
                value={form.keyword_override}
                onChange={(e) =>
                  setForm({ ...form, keyword_override: e.target.value })
                }
                placeholder="food manufacturing company"
              />
            </div>
          </div>
          <div className="form-row">
            <div>
              <label>Positive keyword overrides (optional)</label>
              <input
                value={form.positive_keywords_override}
                onChange={(e) =>
                  setForm({ ...form, positive_keywords_override: e.target.value })
                }
                placeholder="shop floor, ERP extension, batch record"
              />
              <p className="field-hint">
                Comma-separated. Boosts score when found on a lead&apos;s website.
                Merged with defaults in config/icp.yaml.
              </p>
            </div>
            <div>
              <label>Negative keyword overrides (optional)</label>
              <input
                value={form.negative_keywords_override}
                onChange={(e) =>
                  setForm({ ...form, negative_keywords_override: e.target.value })
                }
                placeholder="fully automated, venture-backed startup"
              />
              <p className="field-hint">
                Comma-separated. Lowers score for weak-fit signals (does not
                auto-disqualify).
              </p>
            </div>
          </div>
          <div className="form-row">
            <div>
              <label>Scrape mode</label>
              <div className="mode-toggle">
                <label className="mode-option">
                  <input
                    type="radio"
                    name="enrichment_mode"
                    value="fast"
                    checked={form.enrichment_mode === "fast"}
                    onChange={(e) =>
                      setForm({ ...form, enrichment_mode: e.target.value })
                    }
                  />
                  <span>
                    <strong>Fast</strong> — Quick discovery, lighter contact/pain data
                    (~5–15 min)
                  </span>
                </label>
                <label className="mode-option">
                  <input
                    type="radio"
                    name="enrichment_mode"
                    value="quality"
                    checked={form.enrichment_mode === "quality"}
                    onChange={(e) =>
                      setForm({ ...form, enrichment_mode: e.target.value })
                    }
                  />
                  <span>
                    <strong>Quality</strong> — Full website lookup + job signals
                    (~20–40 min, hotter leads)
                  </span>
                </label>
              </div>
            </div>
          </div>
          <button className="btn" type="submit" disabled={loading || hasActiveJobs}>
            {loading
              ? "Starting..."
              : hasActiveJobs
                ? "Job in progress..."
                : "Start Scrape Job"}
          </button>
        </form>
      </div>

      {config?.metros && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Quick Metro Fill</h3>
          <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
            Click a metro to pre-fill city/state for nationwide discovery.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {config.metros.slice(0, 20).map((m) => (
              <button
                key={`${m.city}-${m.state}`}
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => fillMetro(m)}
              >
                {m.city}, {m.state}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Job History</h3>
        {jobs.length === 0 ? (
          <p className="empty">No scrape jobs yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Industry</th>
                  <th>Mode</th>
                  <th>Location</th>
                  <th>Status</th>
                  <th>Progress</th>
                  <th>Leads</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => {
                  const p = parseScrapeProgress(j);
                  return (
                    <tr key={j.id}>
                      <td>{j.id}</td>
                      <td>{j.industry}</td>
                      <td>
                        <span className={`mode-badge mode-${j.enrichment_mode || "fast"}`}>
                          {j.enrichment_mode === "quality" ? "Quality" : "Fast"}
                        </span>
                      </td>
                      <td>
                        {[j.city, j.state].filter(Boolean).join(", ") || "Nationwide"}
                      </td>
                      <td>
                        <span className={`status-pill status-${j.status}`}>
                          {j.status}
                        </span>
                      </td>
                      <td>
                        <div className="progress-bar-track" style={{ minWidth: 120 }}>
                          <div
                            className="progress-bar-fill"
                            style={{
                              width: `${j.progress_percent ?? p.percent}%`,
                            }}
                          />
                        </div>
                        <div className="job-status" style={{ marginTop: 4 }}>
                          {p.detail}
                        </div>
                      </td>
                      <td>{j.companies_found}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {recentJobs.length > 0 && (
          <div style={{ marginTop: "1.25rem" }}>
            <h4 style={{ marginBottom: "0.75rem" }}>Recent completed / failed</h4>
            {recentJobs.slice(0, 3).map((job) => (
              <ScrapeJobProgress key={job.id} job={job} compact />
            ))}
          </div>
        )}
      </div>
    </>
  );
}
