/** Shared fetch with session cookie + auth redirect. */
async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: {
      ...(options.headers || {}),
    },
  });
  if (res.status === 401 && !url.includes("/api/auth/login")) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/login?next=${next}`;
    throw new Error("Nicht angemeldet");
  }
  return res;
}

async function loadCurrentUser() {
  const res = await apiFetch("/api/auth/me");
  if (!res.ok) return null;
  return res.json();
}

async function logout() {
  await apiFetch("/api/auth/logout", { method: "POST" });
  window.location.href = "/login";
}
