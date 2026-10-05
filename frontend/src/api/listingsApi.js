import axios from "axios";

// Shared axios instance: the Redux thunks and the auth calls below all use it.
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "http://localhost:8486",
  withCredentials: true, // send the HTTP-only session cookie
});

export function errorMessage(err) {
  const detail = err?.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((d) => `${d.loc?.slice(-1)[0] ?? "body"}: ${d.msg}`).join("; ");
  return detail || err?.message || "Request failed";
}

export async function login(email, password) {
  const res = await api.post("/auth/login", { email, password });
  return res.data;
}

export async function logout() {
  const res = await api.post("/auth/logout");
  return res.data;
}

export async function me() {
  const res = await api.get("/auth/me");
  return res.data;
}
