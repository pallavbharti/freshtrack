const BASE = import.meta.env.VITE_API_URL || "/api";
const KEY = "freshtrack.session";

let session = null;
try {
  session = JSON.parse(sessionStorage.getItem(KEY) || "null");
} catch {
  session = null;
}

let onUnauthorized = () => {};

export function getSession() {
  return session;
}

export function setSession(next) {
  session = next;
  try {
    if (next) sessionStorage.setItem(KEY, JSON.stringify(next));
    else sessionStorage.removeItem(KEY);
  } catch {
  }
}

export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  if (session?.token) headers.Authorization = `Bearer ${session.token}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (res.status === 401 && session) {
    setSession(null);
    onUnauthorized();
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.status === 204 ? null : res.json();
}

export async function login(username, password) {
  const body = await request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  const next = { token: body.access_token, role: body.role, username };
  setSession(next);
  return next;
}

export function logout() {
  setSession(null);
}

export const api = {
  products: () => request("/products"),
  stock: () => request("/stock"),
  sales: (productId, days = 28) => request(`/sales?product_id=${productId}&days=${days}`),
  forecast: (productId, days = 7) => request(`/forecast/${productId}?days=${days}`),
  recommendations: () => request("/recommendations"),
  addStock: (body) => request("/stock", { method: "POST", body: JSON.stringify(body) }),
  recordSale: (body) => request("/sales", { method: "POST", body: JSON.stringify(body) }),
};
