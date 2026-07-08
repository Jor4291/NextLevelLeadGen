import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api";

export default function Settings() {
  const [config, setConfig] = useState(null);
  const [sheetId, setSheetId] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet("/config")
      .then((c) => {
        setConfig(c);
        setSheetId(c.google_sheet_id || "");
      })
      .catch((e) => setError(e.message));
  }, []);

  const save = async () => {
    setError("");
    setMessage("");
    try {
      await apiPost("/settings", { google_sheet_id: sheetId });
      setMessage("Settings saved.");
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <>
      <div className="page-header">
        <h1>Settings</h1>
        <p>Google Sheets export and integration configuration.</p>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert alert-info">{message}</div>}

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Google Sheets</h3>
        <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
          Status:{" "}
          {config?.sheets_configured ? (
            <span style={{ color: "var(--success)" }}>Configured</span>
          ) : (
            <span style={{ color: "var(--warning)" }}>Not configured</span>
          )}
        </p>
        <div className="form-row">
          <div>
            <label>Google Sheet ID</label>
            <input
              value={sheetId}
              onChange={(e) => setSheetId(e.target.value)}
              placeholder="From Sheet URL: docs.google.com/spreadsheets/d/SHEET_ID/..."
            />
          </div>
        </div>
        <button className="btn" onClick={save}>
          Save Sheet ID
        </button>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Setup Instructions</h3>
        <ol style={{ fontSize: "0.9rem", color: "var(--muted)", lineHeight: 1.7 }}>
          <li>Create a Google Cloud project and enable Google Sheets API.</li>
          <li>
            Create a service account and download JSON credentials to{" "}
            <code>credentials/google-service-account.json</code>.
          </li>
          <li>
            Share your target Google Sheet with the service account email (Editor
            access).
          </li>
          <li>Paste the Sheet ID above and copy <code>.env.example</code> to <code>.env</code>.</li>
        </ol>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Scoring Weights</h3>
        <pre
          style={{
            background: "var(--bg)",
            padding: "1rem",
            borderRadius: "8px",
            overflow: "auto",
            fontSize: "0.8rem",
          }}
        >
          {JSON.stringify(config?.icp?.scoring_weights, null, 2)}
        </pre>
        <p style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
          Edit <code>config/icp.yaml</code> to tune industries, keywords, and weights.
        </p>
      </div>
    </>
  );
}
