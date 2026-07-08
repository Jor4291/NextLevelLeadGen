const ENTITY_ID = import.meta.env.VITE_ENTITY_ID || "caelvon";
const API_BASE = import.meta.env.VITE_API_URL || "";

function tokenKey() {
  return `${ENTITY_ID}_token`;
}

function userKey() {
  return `${ENTITY_ID}_user`;
}

function authHeaders() {
  const token = localStorage.getItem(tokenKey());
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function handleResponse(res) {
  if (res.status === 401) {
    localStorage.removeItem(tokenKey());
    localStorage.removeItem(userKey());
    window.dispatchEvent(new Event(`${ENTITY_ID}-auth-expired`));
  }
  if (!res.ok) {
    let detail = await res.text();
    try {
      const parsed = JSON.parse(detail);
      detail = parsed.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export async function apiGet(path) {
  const res = await fetch(`${API_BASE}/api${path}`, {
    headers: authHeaders(),
  });
  return handleResponse(res);
}

export async function apiPost(path, body) {
  const res = await fetch(`${API_BASE}/api${path}`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  return handleResponse(res);
}

export async function apiPatch(path, body) {
  const res = await fetch(`${API_BASE}/api${path}`, {
    method: "PATCH",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  return handleResponse(res);
}

export async function login(email, password) {
  return apiPost("/auth/login", { email, password });
}

export async function register(email, password, name) {
  return apiPost("/auth/register", { email, password, name });
}

export function logout() {
  localStorage.removeItem(tokenKey());
  localStorage.removeItem(userKey());
}

export function getStoredUser() {
  try {
    const raw = localStorage.getItem(userKey());
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function storeSession(token, user) {
  localStorage.setItem(tokenKey(), token);
  localStorage.setItem(userKey(), JSON.stringify(user));
}

export function getEntityId() {
  return ENTITY_ID;
}

export function getAuthExpiredEvent() {
  return `${ENTITY_ID}-auth-expired`;
}
