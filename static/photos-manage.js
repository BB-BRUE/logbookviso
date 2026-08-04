const el = {
  select: document.getElementById("toernSelect"),
  list: document.getElementById("photoList"),
  count: document.getElementById("photoCount"),
  upload: document.getElementById("photoUpload"),
  uploadBtn: document.getElementById("photoUploadBtn"),
  back: document.getElementById("backToMap"),
  toast: document.getElementById("toast"),
  importBtn: document.getElementById("importFolderBtn"),
  refreshExisting: document.getElementById("refreshExisting"),
  folderHint: document.getElementById("folderToernHint"),
};

let toastTimer = null;

function showToast(msg) {
  el.toast.hidden = false;
  el.toast.textContent = msg;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.toast.hidden = true;
  }, 3500);
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fmtTime(ms) {
  if (!ms) return "—";
  return new Date(ms).toLocaleString("de-DE");
}

function selectedToernId() {
  const id = Number(el.select.value);
  return Number.isFinite(id) ? id : null;
}

function syncBackLink() {
  const id = selectedToernId();
  el.back.href = id != null ? `/?toern=${id}` : "/";
  if (el.folderHint) {
    el.folderHint.textContent = id != null ? String(id) : "…";
  }
}

async function loadToerns() {
  const res = await fetch("/api/toerns");
  if (!res.ok) throw new Error("Törns konnten nicht geladen werden.");
  const toerns = await res.json();
  el.select.innerHTML = "";
  toerns.forEach((t) => {
    const opt = document.createElement("option");
    opt.value = String(t.id);
    opt.textContent = `${t.name} (${t.id})`;
    el.select.appendChild(opt);
  });
  el.select.disabled = false;

  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get("toern");
  if (fromUrl && [...el.select.options].some((o) => o.value === fromUrl)) {
    el.select.value = fromUrl;
  }
  syncBackLink();
  return toerns;
}

function renderPhotoList(photos) {
  if (!photos.length) {
    el.list.innerHTML = '<p class="hint">Noch keine Fotos für diesen Törn.</p>';
    el.count.textContent = "0 Fotos";
    return;
  }

  el.count.textContent = `${photos.length} Foto${photos.length === 1 ? "" : "s"}`;
  el.list.innerHTML = photos
    .map(
      (p) => `
    <article class="photo-manage-card" data-id="${p.id}">
      <a class="photo-manage-thumb" href="${escapeHtml(p.url)}" target="_blank" rel="noopener">
        <img src="${escapeHtml(p.thumbUrl)}" alt="" loading="lazy" />
      </a>
      <div class="photo-manage-fields">
        <p class="photo-manage-meta">${escapeHtml(p.originalName || "")}</p>
        <label class="field">
          <span>Titel</span>
          <input type="text" class="inp-title" value="${escapeHtml(p.title || "")}" placeholder="Titel" />
        </label>
        <div class="coord-row">
          <label class="field">
            <span>LAT</span>
            <input type="text" class="inp-lat" value="${p.lat}" inputmode="decimal" />
          </label>
          <label class="field">
            <span>LON</span>
            <input type="text" class="inp-lon" value="${p.lon}" inputmode="decimal" />
          </label>
        </div>
        <p class="hint photo-manage-time">Aufnahme: ${escapeHtml(fmtTime(p.takenAtMs))}</p>
        <div class="photo-manage-actions">
          <button type="button" class="btn btn-save">Speichern</button>
          <button type="button" class="btn btn-danger btn-delete">Löschen</button>
        </div>
      </div>
    </article>`
    )
    .join("");
}

async function loadPhotos(toernId) {
  el.list.innerHTML = '<p class="hint">Lade Fotos…</p>';
  const res = await fetch(`/api/photos/list/${toernId}`);
  if (!res.ok) throw new Error("Fotos konnten nicht geladen werden.");
  const data = await res.json();
  renderPhotoList(data.photos || []);
}

async function savePhoto(card) {
  const id = Number(card.dataset.id);
  const title = card.querySelector(".inp-title")?.value?.trim() ?? "";
  const lat = card.querySelector(".inp-lat")?.value?.trim();
  const lon = card.querySelector(".inp-lon")?.value?.trim();

  const res = await fetch(`/api/photos/item/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title, lat, lon }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Speichern fehlgeschlagen.");
  showToast("Gespeichert.");
}

async function deletePhoto(card) {
  const id = Number(card.dataset.id);
  const title = card.querySelector(".inp-title")?.value || `#${id}`;
  if (!window.confirm(`Foto „${title}“ wirklich löschen?`)) return;

  const res = await fetch(`/api/photos/item/${id}`, { method: "DELETE" });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Löschen fehlgeschlagen.");
  card.remove();
  const remaining = el.list.querySelectorAll(".photo-manage-card").length;
  el.count.textContent = `${remaining} Foto${remaining === 1 ? "" : "s"}`;
  if (!remaining) {
    el.list.innerHTML = '<p class="hint">Noch keine Fotos für diesen Törn.</p>';
  }
  showToast("Foto gelöscht.");
}

async function importFromFolder(toernId) {
  el.importBtn.disabled = true;
  try {
    const res = await fetch(`/api/photos/import/${toernId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        refreshExisting: Boolean(el.refreshExisting?.checked),
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Import fehlgeschlagen.");

    const nNew = data.imported?.length ?? 0;
    const nUpd = data.updated?.length ?? 0;
    let msg = `${nNew} neu importiert`;
    if (nUpd) msg += `, ${nUpd} aktualisiert`;
    if (data.warnings?.length) {
      msg += ` · ${data.warnings.length} Hinweise`;
      showToast(`${msg} — ${data.warnings[0]}`);
    } else {
      showToast(msg + ".");
    }
    await loadPhotos(toernId);
  } catch (err) {
    showToast(err.message || "Import fehlgeschlagen");
  } finally {
    el.importBtn.disabled = false;
  }
}

async function uploadPhotos(toernId) {
  const files = document.getElementById("photoFiles")?.files;
  if (!files?.length) {
    showToast("Bitte Dateien auswählen.");
    return;
  }
  const form = new FormData();
  form.append("toern", String(toernId));
  const title = document.getElementById("photoTitle")?.value?.trim();
  const lat = document.getElementById("photoLat")?.value?.trim();
  const lon = document.getElementById("photoLon")?.value?.trim();
  if (title) form.append("title", title);
  if (lat && lon) {
    form.append("lat", lat);
    form.append("lon", lon);
  }
  for (const file of files) form.append("photos", file);

  el.uploadBtn.disabled = true;
  try {
    const res = await fetch("/api/photos/upload", { method: "POST", body: form });
    let data = {};
    try {
      data = await res.json();
    } catch {
      throw new Error(res.status === 413 ? "Upload zu groß." : `HTTP ${res.status}`);
    }
    if (!res.ok) throw new Error(data.error || "Upload fehlgeschlagen.");
    showToast(`${data.count} Foto(s) hochgeladen.`);
    el.upload.reset();
    await loadPhotos(toernId);
  } catch (err) {
    showToast(err.message || "Upload fehlgeschlagen");
  } finally {
    el.uploadBtn.disabled = false;
  }
}

el.list.addEventListener("click", async (e) => {
  const card = e.target.closest(".photo-manage-card");
  if (!card) return;
  if (e.target.closest(".btn-save")) {
    try {
      await savePhoto(card);
    } catch (err) {
      showToast(err.message);
    }
  }
  if (e.target.closest(".btn-delete")) {
    try {
      await deletePhoto(card);
    } catch (err) {
      showToast(err.message);
    }
  }
});

el.select.addEventListener("change", async () => {
  syncBackLink();
  const id = selectedToernId();
  if (id == null) return;
  const url = new URL(window.location.href);
  url.searchParams.set("toern", String(id));
  window.history.replaceState({}, "", url);
  try {
    await loadPhotos(id);
  } catch (err) {
    showToast(err.message);
  }
});

el.upload.addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = selectedToernId();
  if (id == null) {
    showToast("Bitte Törn wählen.");
    return;
  }
  await uploadPhotos(id);
});

el.importBtn?.addEventListener("click", async () => {
  const id = selectedToernId();
  if (id == null) {
    showToast("Bitte Törn wählen.");
    return;
  }
  await importFromFolder(id);
});

async function main() {
  try {
    await loadToerns();
    const id = selectedToernId();
    if (id != null) await loadPhotos(id);
  } catch (err) {
    showToast(err.message || "Fehler beim Laden");
  }
}

main();
