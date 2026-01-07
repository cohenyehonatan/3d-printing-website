const API_BASE =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "";

export function apiFetch(path, options = {}) {
  return fetch(`${API_BASE}${path}`, {
    credentials: "same-origin",
    ...options,
  });
}
