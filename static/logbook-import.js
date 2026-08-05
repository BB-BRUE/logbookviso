const uploadForm = document.getElementById("uploadForm");
const uploadBtn = document.getElementById("uploadBtn");
const uploadStatus = document.getElementById("uploadStatus");
const pickPanel = document.getElementById("pickPanel");
const toernPickList = document.getElementById("toernPickList");
const importBtn = document.getElementById("importBtn");
const selectAllBtn = document.getElementById("selectAllBtn");
const importedList = document.getElementById("importedList");

let uploadId = null;

function showToast(msg) {
  const el = document.getElementById("toast");
  el.hidden = false;
  el.textContent = msg;
  setTimeout(() => {
    el.hidden = true;
  }, 4500);
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function selectedPickIds() {
  return [...toernPickList.querySelectorAll('input[type="checkbox"]:checked')].map((el) =>
    Number(el.dataset.toernId)
  );
}

function renderPickList(toerns) {
  if (!toerns.length) {
    toernPickList.innerHTML = '<p class="hint">Keine Törns in dieser Datei.</p>';
    return;
  }
  toernPickList.innerHTML = toerns
    .map((t) => {
      const imported = t.alreadyImported
        ? ' <span class="admin-toern-chip admin-toern-chip--all">bereits importiert</span>'
        : "";
      return `
      <label class="admin-toern-check">
        <input type="checkbox" data-toern-id="${t.id}" />
        <span><strong>${escapeHtml(t.name)}</strong> (#${t.id}) · ${t.pointsWithCoords} Punkte mit GPS${imported}</span>
      </label>`;
    })
    .join("");
}

async function loadImportedToerns() {
  const res = await apiFetch("/api/toerns");
  if (!res.ok) {
    importedList.innerHTML = '<p class="hint">Konnte Törns nicht laden.</p>';
    return;
  }
  const toerns = await res.json();
  if (!toerns.length) {
    importedList.innerHTML =
      '<p class="hint">Noch keine Törns in der App – Logbook hochladen und importieren.</p>';
    return;
  }
  importedList.innerHTML = toerns
    .map(
      (t) =>
        `<span class="admin-toern-chip">${escapeHtml(t.name)} (#${t.id}) · ${t.pointsWithCoords} GPS-Punkte</span>`
    )
    .join(" ");
}

uploadForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fileInput = document.getElementById("logbookFile");
  const file = fileInput.files?.[0];
  if (!file) {
    showToast("Bitte Datei wählen.");
    return;
  }
  uploadBtn.disabled = true;
  uploadStatus.hidden = false;
  uploadStatus.textContent = "Upload läuft…";
  try {
    const form = new FormData();
    form.append("logbook", file);
    const res = await apiFetch("/api/admin/logbook/upload", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Upload fehlgeschlagen.");
    uploadId = data.uploadId;
    uploadStatus.textContent = `„${data.filename}“ bereit.`;

    const prev = await apiFetch(`/api/admin/logbook/preview?uploadId=${encodeURIComponent(uploadId)}`);
    const preview = await prev.json();
    if (!prev.ok) throw new Error(preview.error || "Vorschau fehlgeschlagen.");

    renderPickList(preview.toerns || []);
    pickPanel.hidden = false;
    showToast(`${(preview.toerns || []).length} Törn(s) in der Datei.`);
  } catch (err) {
    uploadStatus.textContent = err.message || "Fehler";
    showToast(err.message || "Upload fehlgeschlagen");
  } finally {
    uploadBtn.disabled = false;
  }
});

selectAllBtn.addEventListener("click", () => {
  toernPickList.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    cb.checked = true;
  });
});

importBtn.addEventListener("click", async () => {
  if (!uploadId) {
    showToast("Zuerst Logbook hochladen.");
    return;
  }
  const toernIds = selectedPickIds();
  if (!toernIds.length) {
    showToast("Mindestens einen Törn auswählen.");
    return;
  }
  if (
    !window.confirm(
      `${toernIds.length} Törn(s) in die App-Datenbank übernehmen? Vorhandene Track-Daten dieser IDs werden ersetzt.`
    )
  ) {
    return;
  }
  importBtn.disabled = true;
  try {
    const res = await apiFetch("/api/admin/logbook/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ uploadId, toernIds }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Import fehlgeschlagen.");
    let msg = data.message || "Import abgeschlossen.";
    if (data.errors?.length) msg += ` Hinweise: ${data.errors.join("; ")}`;
    showToast(msg);
    uploadId = null;
    pickPanel.hidden = true;
    uploadForm.reset();
    uploadStatus.hidden = true;
    await loadImportedToerns();
  } catch (err) {
    showToast(err.message || "Import fehlgeschlagen");
  } finally {
    importBtn.disabled = false;
  }
});

async function main() {
  const me = await loadCurrentUser();
  if (!me?.isAdmin) {
    window.location.href = "/";
    return;
  }
  await loadImportedToerns();
}

main();
