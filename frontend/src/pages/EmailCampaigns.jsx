import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api";

export default function EmailCampaigns() {
  const [templates, setTemplates] = useState(null);
  const [leads, setLeads] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [brand, setBrand] = useState(null);

  useEffect(() => {
    Promise.all([
      apiGet("/email/templates"),
      apiGet("/leads?status=approved_for_email"),
      apiGet("/config"),
    ])
      .then(([t, l, config]) => {
        setTemplates(t);
        setSubject(t.subject);
        setBody(t.body);
        setLeads(l);
        setBrand(config.brand || null);
      })
      .catch((e) => setError(e.message));
  }, []);

  const send = async () => {
    if (!selected.size) {
      setError("Select at least one lead.");
      return;
    }
    setError("");
    setResult(null);
    try {
      const res = await apiPost("/email/send", {
        lead_ids: Array.from(selected),
        subject,
        body_template: body,
        campaign_name: brand?.campaign_default_name || "Lead Canvas",
      });
      setResult(res);
    } catch (err) {
      setError(err.message);
    }
  };

  const exportCsv = () => {
    const approved = leads.filter((l) => selected.has(l.id) || selected.size === 0);
    const rows = [
      ["Company", "Contact Name", "Email", "Industry", "Practice Fit", "Fit Score", "Tier", "Pain Signals"],
      ...approved.map((l) => [
        l.company_name,
        l.contact_name || "",
        l.email || "",
        l.industry,
        l.practice_fit || "",
        l.fit_score ?? "",
        l.lead_tier || "",
        (l.pain_signals || []).slice(0, 3).join("; "),
      ]),
    ];
    const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${brand?.csv_export_prefix || "leads"}-for-instantly.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <div className="page-header">
        <h1>Email Campaigns</h1>
        <p>
          Canvas approved leads via Resend (built-in) or export CSV for Instantly/GMass.
        </p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {result && (
        <div className="alert alert-info">
          Sent {result.sent} emails. {result.errors?.length ? `${result.errors.length} errors.` : ""}
        </div>
      )}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>{brand?.display_name || "Default"} Template</h3>
        <div className="form-row">
          <div>
            <label>Subject</label>
            <input value={subject} onChange={(e) => setSubject(e.target.value)} />
          </div>
        </div>
        <label>Body (use {"{company_name}"}, {"{contact_name}"} merge fields)</label>
        <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={14} />
        <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.5rem" }}>
          <button className="btn" onClick={send}>
            Send via Resend
          </button>
          <button className="btn btn-secondary" onClick={exportCsv}>
            Export CSV for Instantly
          </button>
        </div>
        <p style={{ fontSize: "0.85rem", color: "var(--muted)", marginTop: "0.75rem" }}>
          Resend requires RESEND_API_KEY in .env. Without it, use CSV export with Instantly.ai
          or GMass (see workflow notes below).
        </p>
      </div>

      {templates && (
        <div className="detail-grid">
          <div className="card">
            <h3 style={{ marginTop: 0 }}>Instantly Workflow</h3>
            <ol style={{ fontSize: "0.9rem", color: "var(--muted)" }}>
              {templates.instantly_workflow.steps.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ol>
          </div>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>GMass Workflow</h3>
            <ol style={{ fontSize: "0.9rem", color: "var(--muted)" }}>
              {templates.gmass_workflow.steps.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ol>
          </div>
        </div>
      )}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Approved for Email ({leads.length})</h3>
        {leads.length === 0 ? (
          <p className="empty">
            Mark leads as &quot;Approved for email&quot; in Lead Detail to add them here.
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th></th>
                <th>Company</th>
                <th>Email</th>
                <th>Practice</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((l) => (
                <tr key={l.id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selected.has(l.id)}
                      onChange={() => {
                        setSelected((prev) => {
                          const next = new Set(prev);
                          if (next.has(l.id)) next.delete(l.id);
                          else next.add(l.id);
                          return next;
                        });
                      }}
                    />
                  </td>
                  <td>{l.company_name}</td>
                  <td>{l.email || "—"}</td>
                  <td>{l.practice_fit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
