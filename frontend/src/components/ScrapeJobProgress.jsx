import { parseScrapeProgress, jobLocation, formatElapsed } from "../utils/scrapeProgress";

function statusClass(status) {
  if (status === "completed") return "status-completed";
  if (status === "failed") return "status-failed";
  if (status === "cancelled") return "status-cancelled";
  if (status === "running") return "status-running";
  return "status-pending";
}

export default function ScrapeJobProgress({
  job,
  compact = false,
  onCancel,
  cancelling = false,
}) {
  const progress = parseScrapeProgress(job);
  const industryLabel =
    job.industry_label || job.industry?.replace(/_/g, " ") || "—";
  const modeLabel =
    job.enrichment_mode === "quality" ? "Quality mode" : "Fast mode";
  const canCancel =
    onCancel &&
    (job.status === "pending" || job.status === "running") &&
    !job.cancel_requested;

  const cancelButton = canCancel ? (
    <button
      type="button"
      className="btn btn-danger btn-sm"
      onClick={() => onCancel(job.id)}
      disabled={cancelling}
    >
      {cancelling ? "Cancelling..." : "Cancel"}
    </button>
  ) : null;

  if (compact) {
    return (
      <div className={`job-progress-card compact ${statusClass(progress.status)}`}>
        <div className="job-progress-header">
          <div>
            <strong>#{job.id}</strong> {industryLabel} · {jobLocation(job)}
            <div className="job-progress-subtitle">{modeLabel}</div>
          </div>
          <div className="job-progress-actions">
            <span className={`status-pill ${statusClass(progress.status)}`}>
              {progress.status}
            </span>
            {cancelButton}
          </div>
        </div>
        <div className="progress-bar-track">
          <div
            className={`progress-bar-fill ${progress.isActive && progress.percent < 100 ? "pulse" : ""}`}
            style={{ width: `${progress.percent}%` }}
          />
        </div>
        <div className="job-progress-meta">
          <span>{progress.phase}</span>
          <span>
            {progress.percent}%
            {job.created_at ? ` · ${formatElapsed(job.created_at)}` : ""}
          </span>
        </div>
        <p className="job-progress-detail">{progress.detail}</p>
      </div>
    );
  }

  return (
    <div className={`job-progress-card ${statusClass(progress.status)}`}>
      <div className="job-progress-header">
        <div>
          <h4 style={{ margin: "0 0 0.25rem" }}>
            Job #{job.id} — {industryLabel}
          </h4>
          <p className="job-progress-subtitle">
            {jobLocation(job)} · {modeLabel}
          </p>
        </div>
        <div className="job-progress-actions">
          <span className={`status-pill ${statusClass(progress.status)}`}>
            {progress.status}
          </span>
          {cancelButton}
        </div>
      </div>

      <div className="progress-steps">
        <span className={progress.percent >= 3 ? "step done" : "step"}>Discover</span>
        <span className={progress.percent >= 20 ? "step done" : "step"}>Websites</span>
        <span className={progress.percent >= 50 ? "step done" : "step"}>Enrich</span>
        <span
          className={
            progress.percent >= 100 && progress.status === "completed"
              ? "step done"
              : "step"
          }
        >
          Done
        </span>
      </div>

      <div className="progress-bar-track">
        <div
          className={`progress-bar-fill ${progress.isActive && progress.percent < 100 ? "pulse" : ""}`}
          style={{ width: `${progress.percent}%` }}
        />
      </div>

      <div className="job-progress-meta">
        <span>
          <strong>{progress.phase}</strong>
          {job.companies_found > 0 ? ` · ${job.companies_found} leads` : ""}
        </span>
        <span>
          {progress.percent}%
          {job.created_at ? ` · ${formatElapsed(job.created_at)}` : ""}
        </span>
      </div>

      <p className="job-progress-detail">{progress.detail}</p>

      {progress.status === "failed" && job.error_message && (
        <p className="job-progress-error">{job.error_message}</p>
      )}
    </div>
  );
}
