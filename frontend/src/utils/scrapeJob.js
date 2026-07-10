export function formatScrapeJobLabel(job, industries = []) {
  if (!job) return "";
  const industryLabel =
    industries.find((i) => i.id === job.industry)?.label ||
    job.industry_label ||
    job.industry;
  const location =
    [job.city, job.state].filter(Boolean).join(", ") || "Nationwide";
  const when = job.completed_at || job.created_at;
  const dateStr = when
    ? new Date(when).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : "";
  const count =
    job.lead_count ?? job.companies_found ?? null;
  const countStr = count != null ? ` · ${count} leads` : "";
  return `#${job.id} · ${industryLabel} · ${location}${dateStr ? ` · ${dateStr}` : ""}${countStr}`;
}

export function formatRelativeTime(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 14) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}
