import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiGet, apiPatch } from "../api";

export default function LeadDetail() {
  const { id } = useParams();
  const [lead, setLead] = useState(null);
  const [users, setUsers] = useState([]);
  const [notes, setNotes] = useState("");
  const [status, setStatus] = useState("new");
  const [assignedTo, setAssignedTo] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    Promise.all([apiGet(`/leads/${id}`), apiGet("/users")])
      .then(([l, u]) => {
        setLead(l);
        setUsers(u);
        setNotes(l.notes || "");
        setStatus(l.status);
        setAssignedTo(l.assigned_to_user_id ? String(l.assigned_to_user_id) : "");
      })
      .catch((e) => setError(e.message));
  }, [id]);

  const save = async () => {
    setError("");
    setSaved(false);
    try {
      const updated = await apiPatch(`/leads/${id}`, {
        notes,
        status,
        assigned_to_user_id: assignedTo ? Number(assignedTo) : null,
      });
      setLead(updated);
      setSaved(true);
    } catch (err) {
      setError(err.message);
    }
  };

  if (!lead) {
    return error ? (
      <div className="alert alert-error">{error}</div>
    ) : (
      <p className="empty">Loading...</p>
    );
  }

  return (
    <>
      <div className="page-header">
        <Link to="/leads" style={{ fontSize: "0.85rem" }}>
          ← Back to inbox
        </Link>
        <h1>{lead.company_name}</h1>
        <p>
          Tier {lead.lead_tier || "—"} · Score {lead.fit_score} · {lead.practice_fit} · {lead.industry}
        </p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {saved && <div className="alert alert-info">Saved.</div>}

      <div className="detail-grid">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Contact</h3>
          <p>
            <strong>Name:</strong> {lead.contact_name || "—"}
            <br />
            <strong>Title:</strong> {lead.contact_title || "—"}
            <br />
            <strong>Email:</strong> {lead.email || "—"}
            <br />
            <strong>Phone:</strong> {lead.phone || "—"}
            <br />
            <strong>Website:</strong>{" "}
            {lead.website ? (
              <a href={lead.website} target="_blank" rel="noreferrer">
                {lead.website}
              </a>
            ) : (
              "—"
            )}
            <br />
            <strong>Employees (est.):</strong> {lead.employee_estimate || "—"}
            <br />
            <strong>Address:</strong> {lead.address || "—"}
          </p>

          {lead.portal_detected && (
            <>
              <h3>Portal / Custom Platform</h3>
              <p>
                <strong>Detected:</strong> Yes
                <br />
                <strong>Type:</strong> {lead.portal_type || "unknown"}
                <br />
                <strong>URLs:</strong>{" "}
                {lead.portal_urls?.length ? (
                  <ul style={{ margin: "0.25rem 0", paddingLeft: "1.25rem" }}>
                    {lead.portal_urls.map((url) => (
                      <li key={url}>
                        <a href={url} target="_blank" rel="noreferrer">
                          {url}
                        </a>
                      </li>
                    ))}
                  </ul>
                ) : (
                  "—"
                )}
              </p>
            </>
          )}

          <h3>Call Notes</h3>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Call outcome, next steps, disqualification reason..."
          />
          <div style={{ marginTop: "0.75rem" }}>
            <label>Assigned to</label>
            <select
              value={assignedTo}
              onChange={(e) => setAssignedTo(e.target.value)}
            >
              <option value="">Unassigned</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </select>
          </div>
          <div style={{ marginTop: "0.75rem" }}>
            <label>Status</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="new">New</option>
              <option value="contacted">Contacted</option>
              <option value="qualified">Qualified</option>
              <option value="not_a_fit">Not a fit</option>
              <option value="exported">Exported</option>
              <option value="approved_for_email">Approved for email</option>
            </select>
          </div>
          <button className="btn" style={{ marginTop: "0.75rem" }} onClick={save}>
            Save
          </button>
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Score Rationale</h3>
          <p style={{ fontSize: "0.9rem" }}>{lead.score_rationale}</p>

          <h3>Pain Signals</h3>
          {lead.pain_signals?.length ? (
            <ul>
              {lead.pain_signals.map((s, i) => (
                <li key={i} style={{ fontSize: "0.85rem", marginBottom: "0.5rem" }}>
                  {s}
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ color: "var(--muted)" }}>No pain signals detected.</p>
          )}

          <h3>Evidence</h3>
          <ul className="evidence-list">
            {(lead.evidence || []).map((e, i) => (
              <li key={i}>
                <div className="type">{e.type}</div>
                <strong>{e.keyword}</strong>
                <p style={{ margin: "0.25rem 0" }}>{e.snippet}</p>
                {e.source_url && (
                  <a href={e.source_url} target="_blank" rel="noreferrer">
                    Source
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}
