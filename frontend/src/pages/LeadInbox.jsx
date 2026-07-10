import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiGet, apiPost } from "../api";

function scoreClass(score, thresholds) {
  const hot = thresholds?.hot ?? 65;
  const review = thresholds?.review ?? 35;
  if (score >= hot) return "score-high";
  if (score >= review) return "score-mid";
  return "score-low";
}

function tierClass(tier) {
  if (tier === "A") return "tier-a";
  if (tier === "B") return "tier-b";
  if (tier === "C") return "tier-c";
  return "tier-d";
}

const EMPTY_FILTERS = {
  min_score: "",
  industry: "",
  status: "",
  tier: "",
  practice_fit: "",
  has_email: false,
  has_phone: false,
  has_contact: false,
  has_portal: false,
  not_exported: false,
  hot_only: false,
  assigned_to_me: false,
  assigned_to_user_id: "",
};

export default function LeadInbox() {
  const [leads, setLeads] = useState([]);
  const [config, setConfig] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [showAll, setShowAll] = useState(false);
  const [filters, setFilters] = useState({
    ...EMPTY_FILTERS,
    min_score: "50",
  });
  const [error, setError] = useState("");
  const [exportMsg, setExportMsg] = useState("");
  const [users, setUsers] = useState([]);

  const thresholds = config?.icp?.thresholds;

  const buildQuery = () => {
    const params = new URLSearchParams();
    if (filters.min_score) params.set("min_score", filters.min_score);
    if (filters.industry) params.set("industry", filters.industry);
    if (filters.status) params.set("status", filters.status);
    if (filters.tier) params.set("tier", filters.tier);
    if (filters.practice_fit) params.set("practice_fit", filters.practice_fit);
    if (filters.has_email) params.set("has_email", "true");
    if (filters.has_phone) params.set("has_phone", "true");
    if (filters.has_contact) params.set("has_contact", "true");
    if (filters.has_portal) params.set("has_portal", "true");
    if (filters.not_exported) params.set("not_exported", "true");
    if (filters.hot_only) params.set("hot_only", "true");
    if (filters.assigned_to_me) params.set("assigned_to_me", "true");
    if (filters.assigned_to_user_id)
      params.set("assigned_to_user_id", filters.assigned_to_user_id);
    const qs = params.toString();
    return `/leads${qs ? `?${qs}` : ""}`;
  };

  const load = () => {
    Promise.all([apiGet(buildQuery()), apiGet("/config"), apiGet("/users")])
      .then(([l, c, u]) => {
        setLeads(l);
        setConfig(c);
        setUsers(u);
      })
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    load();
  }, [filters]);

  const applyPreset = (preset) => {
    if (preset === "hot") {
      setShowAll(false);
      setFilters({
        ...EMPTY_FILTERS,
        status: "new",
        hot_only: true,
        has_contact: true,
      });
      return;
    }
    if (preset === "ready") {
      setShowAll(false);
      setFilters({
        ...EMPTY_FILTERS,
        min_score: String(thresholds?.qualified ?? 50),
        has_phone: true,
        not_exported: true,
        status: "new",
      });
      return;
    }
    if (preset === "mine") {
      setShowAll(false);
      setFilters({
        ...EMPTY_FILTERS,
        assigned_to_me: true,
      });
      return;
    }
    if (preset === "qualified") {
      setShowAll(false);
      setFilters({
        ...EMPTY_FILTERS,
        min_score: String(thresholds?.qualified ?? 50),
      });
      return;
    }
    if (preset === "portal") {
      setShowAll(false);
      setFilters({
        ...EMPTY_FILTERS,
        has_portal: true,
        min_score: String(thresholds?.review ?? 35),
      });
      return;
    }
    if (preset === "all") {
      setShowAll(true);
      setFilters({ ...EMPTY_FILTERS });
    }
  };

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === leads.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(leads.map((l) => l.id)));
    }
  };

  const exportLeads = async () => {
    setError("");
    setExportMsg("");
    try {
      const result = await apiPost("/leads/export", {
        lead_ids: selected.size ? Array.from(selected) : [],
        include_low_tier: selected.size > 0,
        include_no_contact: selected.size > 0,
      });
      setExportMsg(`Exported ${result.exported_count} leads to Google Sheets.`);
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const topPainSignal = (lead) => {
    const signals = lead.pain_signals || [];
    if (!signals.length) return "—";
    const first = signals[0];
    return first.length > 60 ? `${first.slice(0, 57)}...` : first;
  };

  return (
    <>
      <div className="page-header">
        <h1>Lead Inbox</h1>
        <p>Review scored leads, add call notes, and export to Google Sheets.</p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {exportMsg && <div className="alert alert-info">{exportMsg}</div>}

      <div className="preset-buttons">
        <button type="button" className="btn btn-sm" onClick={() => applyPreset("hot")}>
          Hot leads
        </button>
        <button type="button" className="btn btn-sm" onClick={() => applyPreset("ready")}>
          Ready to call
        </button>
        <button type="button" className="btn btn-sm" onClick={() => applyPreset("mine")}>
          My leads
        </button>
        <button type="button" className="btn btn-sm" onClick={() => applyPreset("qualified")}>
          Qualified ({thresholds?.qualified ?? 50}+)
        </button>
        <button type="button" className="btn btn-sm" onClick={() => applyPreset("portal")}>
          Has portal
        </button>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => applyPreset("all")}
        >
          Show all
        </button>
      </div>

      <div className="filters">
        <div>
          <label>Min Score</label>
          <input
            type="number"
            min="0"
            max="100"
            value={filters.min_score}
            onChange={(e) =>
              setFilters({ ...filters, min_score: e.target.value, hot_only: false })
            }
          />
        </div>
        <div>
          <label>Tier</label>
          <select
            value={filters.tier}
            onChange={(e) =>
              setFilters({ ...filters, tier: e.target.value, hot_only: false })
            }
          >
            <option value="">All</option>
            <option value="A">A — Hot</option>
            <option value="B">B — Qualified</option>
            <option value="C">C — Review</option>
            <option value="D">D — Low</option>
          </select>
        </div>
        <div>
          <label>Industry</label>
          <select
            value={filters.industry}
            onChange={(e) =>
              setFilters({ ...filters, industry: e.target.value })
            }
          >
            <option value="">All</option>
            {config?.industries?.map((i) => (
              <option key={i.id} value={i.id}>
                {i.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label>Practice fit</label>
          <select
            value={filters.practice_fit}
            onChange={(e) =>
              setFilters({ ...filters, practice_fit: e.target.value })
            }
          >
            <option value="">All</option>
            <option value="Process Opt">Process Opt</option>
            <option value="Custom Software">Custom Software</option>
            <option value="Both">Both</option>
            <option value="Needs Review">Needs Review</option>
          </select>
        </div>
        <div>
          <label>Assigned to</label>
          <select
            value={filters.assigned_to_user_id}
            onChange={(e) =>
              setFilters({
                ...filters,
                assigned_to_user_id: e.target.value,
                assigned_to_me: false,
              })
            }
          >
            <option value="">Anyone</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label>Status</label>
          <select
            value={filters.status}
            onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          >
            <option value="">All</option>
            <option value="new">New</option>
            <option value="contacted">Contacted</option>
            <option value="qualified">Qualified</option>
            <option value="not_a_fit">Not a fit</option>
            <option value="exported">Exported</option>
            <option value="approved_for_email">Approved for email</option>
          </select>
        </div>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={filters.has_email}
            onChange={(e) =>
              setFilters({ ...filters, has_email: e.target.checked })
            }
          />
          Has email
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={filters.has_phone}
            onChange={(e) =>
              setFilters({ ...filters, has_phone: e.target.checked })
            }
          />
          Has phone
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={filters.has_portal}
            onChange={(e) =>
              setFilters({ ...filters, has_portal: e.target.checked })
            }
          />
          Has portal
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={filters.not_exported}
            onChange={(e) =>
              setFilters({ ...filters, not_exported: e.target.checked })
            }
          />
          Not exported
        </label>
        <button className="btn" onClick={exportLeads}>
          Export {selected.size ? `(${selected.size})` : "Callable"}
        </button>
      </div>

      {!showAll && filters.min_score === "50" && !filters.hot_only && (
        <p className="filter-hint">
          Showing qualified leads (score 50+). Click <strong>Show all</strong> to see every lead.
        </p>
      )}

      <div className="card table-wrap">
        {leads.length === 0 ? (
          <p className="empty">No leads match filters.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    checked={selected.size === leads.length && leads.length > 0}
                    onChange={toggleAll}
                  />
                </th>
                <th>Company</th>
                <th>Tier</th>
                <th>Score</th>
                <th>Practice</th>
                <th>Top signal</th>
                <th>Contact</th>
                <th>Assigned</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((l) => (
                <tr key={l.id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selected.has(l.id)}
                      onChange={() => toggleSelect(l.id)}
                    />
                  </td>
                  <td>
                    <Link to={`/leads/${l.id}`}>{l.company_name}</Link>
                    <div style={{ fontSize: "0.8rem", color: "var(--muted)" }}>
                      {[l.city, l.state].filter(Boolean).join(", ")} · {l.industry}
                      {l.portal_detected && (
                        <span className="portal-badge"> Portal</span>
                      )}
                    </div>
                  </td>
                  <td>
                    <span className={`tier-badge ${tierClass(l.lead_tier)}`}>
                      {l.lead_tier || "—"}
                    </span>
                  </td>
                  <td>
                    <span
                      className={`score-badge ${scoreClass(l.fit_score, thresholds)}`}
                    >
                      {l.fit_score}
                    </span>
                  </td>
                  <td>{l.practice_fit}</td>
                  <td className="pain-signal-cell">{topPainSignal(l)}</td>
                  <td>
                    <div>{l.contact_name || "—"}</div>
                    <div style={{ fontSize: "0.8rem", color: "var(--muted)" }}>
                      {l.email || l.phone || "—"}
                    </div>
                  </td>
                  <td>{l.assigned_to_name || "—"}</td>
                  <td>
                    <span className="status-pill">{l.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
