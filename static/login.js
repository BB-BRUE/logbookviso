const form = document.getElementById("loginForm");
const errEl = document.getElementById("loginError");

async function tryAlreadyLoggedIn() {
  const res = await fetch("/api/auth/me", { credentials: "same-origin" });
  if (res.ok) {
    const params = new URLSearchParams(window.location.search);
    window.location.href = params.get("next") || "/";
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errEl.hidden = true;
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;
  const res = await fetch("/api/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    errEl.hidden = false;
    errEl.textContent = data.error || "Anmeldung fehlgeschlagen.";
    return;
  }
  const params = new URLSearchParams(window.location.search);
  window.location.href = params.get("next") || "/";
});

tryAlreadyLoggedIn();
