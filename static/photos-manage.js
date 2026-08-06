const el = {
  select: document.getElementById("toernSelect"),
  list: document.getElementById("photoList"),
  count: document.getElementById("photoCount"),
  upload: document.getElementById("photoUpload"),
  uploadBtn: document.getElementById("photoUploadBtn"),
  uploadWait: document.getElementById("photoUploadWait"),
  filesGallery: document.getElementById("photoFilesGallery"),
  filesDisk: document.getElementById("photoFilesDisk"),
  filesHint: document.getElementById("photoFilesHint"),
  back: document.getElementById("backToMap"),
  toast: document.getElementById("toast"),
  importBtn: document.getElementById("importFolderBtn"),
  refreshExisting: document.getElementById("refreshExisting"),
  folderHint: document.getElementById("folderToernHint"),
  filterUnlocated: document.getElementById("filterUnlocatedOnly"),
};

let allPhotos = [];

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
  const toerns = await fetchToerns();
  fillToernSelect(el.select, toerns, "manage");
  applyToernFromUrl(el.select);
  syncBackLink();
  return toerns;
}

function visiblePhotos() {
  if (!el.filterUnlocated?.checked) return allPhotos;
  return allPhotos.filter((p) => !p.hasCoordinates);
}

function renderPhotoList(photos) {
  if (!photos.length) {
    const msg = el.filterUnlocated?.checked
      ? "Keine Medien ohne Koordinaten für diesen Törn."
      : "Noch keine Medien für diesen Törn.";
    el.list.innerHTML = `<p class="hint">${msg}</p>`;
    el.count.textContent = "0 Medien";
    return;
  }

  el.count.textContent = `${photos.length} Medium${photos.length === 1 ? "" : "en"}`;
  el.list.innerHTML = photos
    .map(
      (p) => {
        const ro = !p.canEdit;
        const ownerHint = p.uploadedBy
          ? `Hochgeladen von ${escapeHtml(p.uploadedBy)}`
          : p.uploadedByUserId == null
            ? "Legacy-Foto (nur Admin bearbeitbar)"
            : "";
        return `
    <article class="photo-manage-card${ro ? " photo-manage-readonly" : ""}" data-id="${p.id}">
      <a class="photo-manage-thumb" href="${escapeHtml(p.url)}" target="_blank" rel="noopener">
        <img src="${escapeHtml(p.thumbUrl)}" alt="" loading="lazy" />
      </a>
      <div class="photo-manage-fields">
        <p class="photo-manage-meta">${escapeHtml(p.originalName || "")}</p>
        ${ownerHint ? `<p class="hint">${ownerHint}</p>` : ""}
        ${!p.hasCoordinates ? '<p class="hint photo-manage-no-gps">Ohne Koordinaten</p>' : ""}
        <label class="field">
          <span>Titel</span>
          <input type="text" class="inp-title" value="${escapeHtml(p.title || "")}" placeholder="Titel" ${ro ? "disabled" : ""} />
        </label>
        <div class="coord-row">
          <label class="field">
            <span>LAT</span>
            <input type="text" class="inp-lat" value="${p.lat === "" || p.lat == null ? "" : p.lat}" inputmode="decimal" placeholder="optional" ${ro ? "disabled" : ""} />
          </label>
          <label class="field">
            <span>LON</span>
            <input type="text" class="inp-lon" value="${p.lon === "" || p.lon == null ? "" : p.lon}" inputmode="decimal" placeholder="optional" ${ro ? "disabled" : ""} />
          </label>
        </div>
        <p class="hint photo-manage-time">Aufnahme: ${escapeHtml(fmtTime(p.takenAtMs))}</p>
        <div class="photo-manage-actions">
          <button type="button" class="btn btn-save" ${ro ? "disabled" : ""}>Speichern</button>
          <button type="button" class="btn btn-danger btn-delete" ${ro ? "disabled" : ""}>Löschen</button>
        </div>
      </div>
    </article>`;
      }
    )
    .join("");
}

async function loadPhotos(toernId) {
  el.list.innerHTML = '<p class="hint">Lade Fotos…</p>';
  const res = await apiFetch(`/api/photos/list/${toernId}`);
  if (!res.ok) throw new Error("Fotos konnten nicht geladen werden.");
  const data = await res.json();
  allPhotos = data.photos || [];
  renderPhotoList(visiblePhotos());
}

async function savePhoto(card) {
  const id = Number(card.dataset.id);
  const title = card.querySelector(".inp-title")?.value?.trim() ?? "";
  const lat = card.querySelector(".inp-lat")?.value?.trim();
  const lon = card.querySelector(".inp-lon")?.value?.trim();

  const body = { title };
  if (lat === "" && lon === "") {
    body.clearCoordinates = true;
  } else if (lat || lon) {
    if (!lat || !lon) {
      showToast("LAT und LON gemeinsam ausfüllen oder beide leer lassen.");
      return;
    }
    body.lat = lat;
    body.lon = lon;
  }

  const res = await apiFetch(`/api/photos/item/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Speichern fehlgeschlagen.");
  showToast("Gespeichert.");
  await loadPhotos(selectedToernId());
}

async function deletePhoto(card) {
  const id = Number(card.dataset.id);
  const title = card.querySelector(".inp-title")?.value || `#${id}`;
  if (!window.confirm(`Foto „${title}“ wirklich löschen?`)) return;

  const res = await apiFetch(`/api/photos/item/${id}`, { method: "DELETE" });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Löschen fehlgeschlagen.");
  await loadPhotos(selectedToernId());
  showToast("Foto gelöscht.");
}

async function importFromFolder(toernId) {
  el.importBtn.disabled = true;
  try {
    const res = await apiFetch(`/api/photos/import/${toernId}`, {
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

function selectedUploadFiles() {
  const gallery = el.filesGallery?.files;
  const disk = el.filesDisk?.files;
  if (disk?.length) return { files: disk, source: "Dateien" };
  if (gallery?.length) return { files: gallery, source: "Galerie" };
  return { files: null, source: null };
}

function syncFilePickHint() {
  if (!el.filesHint) return;
  const { files, source } = selectedUploadFiles();
  if (!files?.length) {
    el.filesHint.hidden = true;
    el.filesHint.textContent = "";
    return;
  }
  const n = files.length;
  el.filesHint.hidden = false;
  el.filesHint.textContent = `${n} Datei${n === 1 ? "" : "en"} aus ${source} gewählt.`;
}

function onFilePickChange(active, other) {
  if (active?.files?.length && other) other.value = "";
  syncFilePickHint();
}

/** Pro Request unter typischen Reverse-Proxy-Limits bleiben (Nginx 413). */
const UPLOAD_BATCH_MAX_BYTES = 40 * 1024 * 1024;
const UPLOAD_BATCH_MAX_FILES = 8;

function buildUploadBatches(files) {
  const batches = [];
  let batch = [];
  let batchBytes = 0;
  for (const file of files) {
    const size = Number(file.size) || 0;
    const wouldExceed =
      batch.length > 0 &&
      (batch.length >= UPLOAD_BATCH_MAX_FILES ||
        batchBytes + size > UPLOAD_BATCH_MAX_BYTES);
    if (wouldExceed) {
      batches.push(batch);
      batch = [];
      batchBytes = 0;
    }
    batch.push(file);
    batchBytes += size;
  }
  if (batch.length) batches.push(batch);
  return batches;
}

function setUploadWaitText(text) {
  const tip = el.uploadWait?.querySelector(".upload-wait-text");
  if (tip) tip.textContent = text;
}

async function postPhotoBatch(toernId, files, meta) {
  const form = new FormData();
  form.append("toern", String(toernId));
  if (meta.title) form.append("title", meta.title);
  if (meta.lat && meta.lon) {
    form.append("lat", meta.lat);
    form.append("lon", meta.lon);
  }
  for (const file of files) form.append("photos", file);

  const res = await apiFetch("/api/photos/upload", { method: "POST", body: form });
  let data = {};
  try {
    data = await res.json();
  } catch {
    throw new Error(
      res.status === 413
        ? "Upload zu groß (Proxy-Limit). Weniger/kleinere Dateien oder SWAG client_max_body_size prüfen."
        : `HTTP ${res.status}`
    );
  }
  if (!res.ok) throw new Error(data.error || "Upload fehlgeschlagen.");
  return data;
}

async function uploadPhotos(toernId) {
  const { files } = selectedUploadFiles();
  if (!files?.length) {
    showToast("Bitte Dateien aus Galerie oder Dateimanager wählen.");
    return;
  }
  const title = document.getElementById("photoTitle")?.value?.trim();
  const lat = document.getElementById("photoLat")?.value?.trim();
  const lon = document.getElementById("photoLon")?.value?.trim();
  const meta = { title, lat, lon };
  const batches = buildUploadBatches([...files]);

  el.uploadBtn.disabled = true;
  if (el.uploadWait) el.uploadWait.hidden = false;
  let totalSaved = 0;
  const allErrors = [];
  try {
    for (let i = 0; i < batches.length; i++) {
      setUploadWaitText(
        batches.length === 1
          ? "Bitte warten – Upload läuft…"
          : `Bitte warten – Upload ${i + 1}/${batches.length}…`
      );
      const data = await postPhotoBatch(toernId, batches[i], meta);
      totalSaved += data.count || 0;
      if (Array.isArray(data.errors) && data.errors.length) {
        allErrors.push(...data.errors);
      }
    }
    if (totalSaved === 0 && allErrors.length) {
      throw new Error(allErrors[0]);
    }
    const msg =
      allErrors.length > 0
        ? `${totalSaved} hochgeladen, ${allErrors.length} Fehler.`
        : `${totalSaved} Foto(s) hochgeladen.`;
    showToast(msg);
    el.upload.reset();
    syncFilePickHint();
    await loadPhotos(toernId);
  } catch (err) {
    showToast(err.message || "Upload fehlgeschlagen");
    if (totalSaved > 0) {
      try {
        await loadPhotos(toernId);
      } catch {
        /* ignore */
      }
    }
  } finally {
    setUploadWaitText("Bitte warten – Upload läuft…");
    el.uploadBtn.disabled = false;
    if (el.uploadWait) el.uploadWait.hidden = true;
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

el.filesGallery?.addEventListener("change", () => {
  onFilePickChange(el.filesGallery, el.filesDisk);
});
el.filesDisk?.addEventListener("change", () => {
  onFilePickChange(el.filesDisk, el.filesGallery);
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

el.filterUnlocated?.addEventListener("change", () => {
  renderPhotoList(visiblePhotos());
});

async function main() {
  try {
    await loadCurrentUser();
  } catch {
    return;
  }
  try {
    await loadToerns();
    const id = selectedToernId();
    if (id != null) await loadPhotos(id);
  } catch (err) {
    showToast(err.message || "Fehler beim Laden");
  }
}

main();
