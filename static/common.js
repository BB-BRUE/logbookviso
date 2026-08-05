/**
 * Gemeinsame Frontend-Hilfen (Toast, Escaping, Törn-API).
 * Wird nach auth.js auf Admin-, Foto- und Karten-Seiten geladen.
 */

let _toastTimer = null;

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

/**
 * @param {string} msg
 * @param {{ duration?: number, elementId?: string }} [opts]
 */
function showToast(msg, opts = {}) {
  const { duration = 3500, elementId = "toast" } = opts;
  const el = document.getElementById(elementId);
  if (!el) return;
  el.hidden = false;
  el.textContent = msg;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => {
    el.hidden = true;
  }, duration);
}

async function fetchToerns() {
  const res = await apiFetch("/api/toerns");
  if (!res.ok) throw new Error("Törns konnten nicht geladen werden.");
  return res.json();
}

/**
 * Törn-Dropdown befüllen.
 * @param {HTMLSelectElement} select
 * @param {Array} toerns
 * @param {"map"|"manage"} mode – Karte gruppiert nach GPS, Verwaltung flach
 */
function fillToernSelect(select, toerns, mode = "manage") {
  select.innerHTML = "";

  if (mode === "map") {
    const usable = toerns.filter((t) => t.pointsWithCoords > 0);
    const empty = toerns.filter((t) => t.pointsWithCoords === 0);
    if (!usable.length) {
      select.innerHTML = "<option>Keine Tracks mit Koordinaten</option>";
      select.disabled = true;
      return { toerns, hasUsable: false };
    }
    usable.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = String(t.id);
      opt.textContent = `${t.name} (${t.pointsWithCoords} Pts)`;
      select.appendChild(opt);
    });
    if (empty.length) {
      const group = document.createElement("optgroup");
      group.label = "Ohne Koordinaten";
      empty.forEach((t) => {
        const opt = document.createElement("option");
        opt.value = String(t.id);
        opt.textContent = `${t.name} (0)`;
        opt.disabled = true;
        group.appendChild(opt);
      });
      select.appendChild(group);
    }
    select.disabled = false;
    return { toerns, hasUsable: true };
  }

  toerns.forEach((t) => {
    const opt = document.createElement("option");
    opt.value = String(t.id);
    opt.textContent = `${t.name} (${t.id})`;
    select.appendChild(opt);
  });
  select.disabled = false;
  return { toerns, hasUsable: toerns.length > 0 };
}

/** ?toern= aus URL auf Select anwenden. */
function applyToernFromUrl(select) {
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get("toern");
  if (fromUrl && [...select.options].some((o) => o.value === fromUrl)) {
    select.value = fromUrl;
  }
  const id = Number(select.value);
  return Number.isFinite(id) ? id : null;
}

async function requireAdminOrRedirect() {
  const me = await loadCurrentUser();
  if (!me?.isAdmin) {
    window.location.href = "/";
    return null;
  }
  return me;
}
