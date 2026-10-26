import axios from "axios";

// HW7: JWT bearer token instead of the HW4 session cookie. The token is kept in
// sessionStorage so a page refresh keeps you logged in until the tab is closed.
const TOKEN_KEY = "s9486_token";

export function getToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function setToken(token) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage blocked: the token just lives for this page load */
  }
}

// Shared axios instance: the Redux thunks and the auth calls below all use it.
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "http://localhost:8486",
});

api.interceptors.request.use((cfg) => {
  const token = getToken();
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

export function errorMessage(err) {
  const detail = err?.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((d) => `${d.loc?.slice(-1)[0] ?? "body"}: ${d.msg}`).join("; ");
  return detail || err?.message || "Request failed";
}

export async function login(username, password) {
  const res = await api.post("/auth/login", { username, password });
  setToken(res.data.access_token);
  return me();
}

export async function logout() {
  // JWTs are stateless, so logging out just forgets the token on this side.
  setToken(null);
}

export async function me() {
  const res = await api.get("/auth/me");
  return res.data;
}
