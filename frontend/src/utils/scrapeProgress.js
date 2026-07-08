const PHASES = {
  pending: { label: "Queued", order: 0 },
  running: { label: "Running", order: 1 },
  completed: { label: "Completed", order: 2 },
  failed: { label: "Failed", order: 3 },
  cancelled: { label: "Cancelled", order: 4 },
};

function parsePercentFromMessage(message, status) {
  const msg = message || "";
  const enriching = msg.match(/Enriching (\d+)\/(\d+)/i);
  const websiteLookup = msg.match(/Website lookup (\d+)\/(\d+)/i);
  const resolving = msg.match(/Resolving websites for (\d+)/i);
  const found = msg.match(/Found (\d+) companies/i);

  if (enriching) {
    const current = Number(enriching[1]);
    const total = Number(enriching[2]);
    return Math.min(99, Math.round(50 + (current / Math.max(total, 1)) * 49));
  }
  if (found) return 50;
  if (websiteLookup) {
    const current = Number(websiteLookup[1]);
    const total = Number(websiteLookup[2]);
    return Math.min(49, Math.round(14 + (current / Math.max(total, 1)) * 35));
  }
  if (resolving) return 14;
  if (/Searching Google Maps/i.test(msg)) return 6;
  if (/Trying Bing/i.test(msg)) return 10;
  if (/Starting discovery/i.test(msg)) return 2;
  if (status === "pending") return 0;
  if (status === "running") return 8;
  return 100;
}

export function parseScrapeProgress(job) {
  const status = job?.status || "pending";
  const message = job?.progress_message || "";
  const error = job?.error_message || "";

  let percent =
    job?.progress_percent != null && job.progress_percent > 0
      ? job.progress_percent
      : parsePercentFromMessage(message, status);

  let phase = "Starting";
  let detail = message || "Waiting to start...";

  if (status === "pending") {
    percent = 0;
    phase = "Queued";
    detail = "Waiting for worker...";
  } else if (status === "completed") {
    percent = 100;
    phase = "Complete";
    detail = message || `Finished — ${job.companies_found || 0} leads created.`;
  } else if (status === "failed") {
    percent = 100;
    phase = "Failed";
    detail = error || message || "Job failed.";
  } else if (status === "cancelled") {
    percent = 100;
    phase = "Cancelled";
    detail = message || "Job cancelled.";
  } else if (status === "running") {
    if (/Enriching/i.test(message)) {
      phase = "Enriching & scoring";
    } else if (/Website lookup|Resolving websites/i.test(message)) {
      phase = "Resolving websites";
    } else if (/Searching Google Maps|Trying Bing|Starting discovery/i.test(message)) {
      phase = "Discovery";
    } else {
      phase = "Running";
    }
    detail = message || "Working...";
  }

  return {
    status,
    percent: Math.min(100, Math.max(0, percent)),
    phase,
    detail,
    phaseMeta: PHASES[status] || PHASES.pending,
    isActive: status === "pending" || status === "running",
  };
}

export function jobLocation(job) {
  return [job.city, job.state].filter(Boolean).join(", ") || "Nationwide";
}

export function formatElapsed(createdAt) {
  if (!createdAt) return "";
  const start = new Date(createdAt.endsWith("Z") ? createdAt : createdAt + "Z");
  const seconds = Math.floor((Date.now() - start.getTime()) / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const rem = seconds % 60;
  if (minutes < 60) return `${minutes}m ${rem}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}
