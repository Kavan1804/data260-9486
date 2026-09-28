import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "http://localhost:8486",
  withCredentials: true, // send the HTTP-only session cookie
});

export function errorMessage(err) {
  const detail = err?.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  return detail || err?.message || "Request failed";
}

export async function fetchListings() {
  const res = await api.get("/listings");
  return res.data;
}

export async function fetchListingById(id) {
  const res = await api.get(`/listings/${id}`);
  return res.data;
}

export async function createListing(payload) {
  const res = await api.post("/listings", payload);
  return res.data;
}

export async function updateListing(id, payload) {
  const res = await api.put(`/listings/${id}`, payload);
  return res.data;
}

export async function deleteListing(id) {
  const res = await api.delete(`/listings/${id}`);
  return res.data;
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
