export function slugifyIndustry(text) {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 64);
}

const INDUSTRY_ALIASES = {
  logistics: "distribution",
  "3pl": "distribution",
  trucking: "transport",
  fleet: "transport",
  freight: "transport",
  food: "food_beverage",
  beverage: "food_beverage",
  healthcare: "healthcare_ops",
  construction: "construction",
  utilities: "utilities",
  oil: "oil_gas",
  gas: "oil_gas",
  energy: "oil_gas",
};

function tokenize(text) {
  return text
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((word) => word.length > 2);
}

function scoreIndustryMatch(input, industry) {
  const trimmed = input.trim().toLowerCase();
  const slug = slugifyIndustry(trimmed);
  const label = industry.label.toLowerCase();
  const id = industry.id.toLowerCase();
  const idWords = id.replace(/_/g, " ");

  if (id === slug || label === trimmed) return 100;
  if (label.includes(trimmed) || trimmed.includes(label)) return 80;
  if (idWords.includes(trimmed) || trimmed.includes(idWords)) return 70;

  const inputWords = tokenize(trimmed);
  const labelWords = tokenize(label);
  const idTokens = tokenize(idWords);
  const overlap = inputWords.filter(
    (word) => labelWords.includes(word) || idTokens.includes(word)
  ).length;
  if (!overlap) return 0;
  return 40 + overlap * 10;
}

export function resolveIndustryFromInput(input, industries = []) {
  const trimmed = input.trim();
  if (!trimmed) {
    return { id: "", label: "" };
  }

  const slug = slugifyIndustry(trimmed);
  const aliasId = INDUSTRY_ALIASES[slug];
  if (aliasId) {
    const aliasMatch = industries.find((industry) => industry.id === aliasId);
    if (aliasMatch) {
      return { id: aliasMatch.id, label: aliasMatch.label, matched: true };
    }
  }

  let best = null;
  let bestScore = 0;

  for (const industry of industries) {
    const score = scoreIndustryMatch(trimmed, industry);
    if (score > bestScore) {
      best = industry;
      bestScore = score;
    }
  }

  if (best && bestScore >= 70) {
    return { id: best.id, label: best.label, matched: true };
  }

  return { id: slug, label: trimmed, matched: false };
}

export function describeIndustrySearch(resolved, industries = []) {
  if (!resolved?.id) return "";
  const cfg = industries.find((i) => i.id === resolved.id);
  if (cfg?.search_queries?.length) {
    return cfg.search_queries.slice(0, 2).join(" · ");
  }
  return `${resolved.label} company · ${resolved.label}`;
}
