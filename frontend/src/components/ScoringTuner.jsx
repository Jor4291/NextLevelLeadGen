import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api";

const SECTION_ORDER = [
  "scoring_weights",
  "negative_weights",
  "thresholds",
  "employee_bands",
];

function isOverridden(section, key, scoring) {
  return Object.prototype.hasOwnProperty.call(
    scoring?.overrides?.[section] || {},
    key
  );
}

export default function ScoringTuner() {
  const [scoring, setScoring] = useState(null);
  const [values, setValues] = useState({});
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = () => {
    setLoading(true);
    apiGet("/icp/scoring")
      .then((data) => {
        setScoring(data);
        setValues(data.values || {});
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleChange = (section, key, rawValue) => {
    setValues((prev) => ({
      ...prev,
      [section]: {
        ...prev[section],
        [key]: rawValue === "" ? "" : Number(rawValue),
      },
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const updated = await apiPost("/icp/scoring", values);
      setScoring(updated);
      setValues(updated.values || {});
      setMessage("Scoring settings saved. New scrapes will use these weights.");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (
      !window.confirm(
        "Reset all scoring weights to icp.yaml defaults? This removes config/icp_overrides.yaml values."
      )
    ) {
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const updated = await apiPost("/icp/scoring/reset", {});
      setScoring(updated);
      setValues(updated.values || {});
      setMessage("Scoring settings reset to defaults.");
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="empty">Loading scoring settings...</p>;
  }

  if (!scoring) {
    return null;
  }

  return (
    <div className="card">
      <div className="scoring-header">
        <div>
          <h3 style={{ marginTop: 0 }}>ICP Scoring Tuner</h3>
          <p style={{ color: "var(--muted)", fontSize: "0.9rem", marginBottom: 0 }}>
            Adjust how leads are scored 0–100. Changes are saved to{" "}
            <code>{scoring.overrides_path}</code> and apply to new scrapes
            immediately.
          </p>
        </div>
        <div className="scoring-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={handleReset}
            disabled={saving}
          >
            Reset to defaults
          </button>
          <button type="button" className="btn" onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : "Save scoring"}
          </button>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert alert-info">{message}</div>}

      {SECTION_ORDER.map((section) => (
        <div key={section} className="scoring-section">
          <h4>{scoring.sections?.[section] || section}</h4>
          <div className="scoring-grid">
            {Object.entries(scoring.fields?.[section] || {}).map(([key, meta]) => {
              const defaultValue = scoring.defaults?.[section]?.[key];
              const overridden = isOverridden(section, key, scoring);
              return (
                <div key={key} className="scoring-field">
                  <label htmlFor={`${section}-${key}`}>
                    {meta.label}
                    {overridden && <span className="override-badge">custom</span>}
                  </label>
                  <input
                    id={`${section}-${key}`}
                    type="number"
                    min={meta.min}
                    max={meta.max}
                    step={section === "employee_bands" ? 1 : 0.5}
                    value={values?.[section]?.[key] ?? ""}
                    onChange={(e) => handleChange(section, key, e.target.value)}
                  />
                  <p className="field-hint">{meta.description}</p>
                  <p className="field-hint scoring-default">
                    Default: {defaultValue ?? "—"}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
