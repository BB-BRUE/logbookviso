const createForm = document.getElementById("createUserForm");
const userList = document.getElementById("userList");
const newToerns = document.getElementById("newToerns");

let allToerns = [];
let users = [];

function toernLabel(t) {
  return `${t.name} (#${t.id})`;
}

function toernById(id) {
  return allToerns.find((t) => t.id === id);
}

/** Kurztext + Chips für zugeordnete Törns (Inhalt ohne äußeres p) */
function toernSummaryInner(u) {
  if (u.role === "admin") {
    return '<span class="admin-toern-summary-label">Zugriff:</span> <span class="admin-toern-chip admin-toern-chip--all">Alle Törns (Admin)</span>';
  }
  const ids = u.toernIds || [];
  if (!ids.length) {
    return '<span class="admin-toern-summary-label">Zugeordnet:</span> <span class="hint">Keine Törns</span>';
  }
  const chips = ids
    .map((id) => {
      const t = toernById(id);
      const label = t ? escapeHtml(toernLabel(t)) : escapeHtml(`#${id}`);
      return `<span class="admin-toern-chip">${label}</span>`;
    })
    .join(" ");
  return `<span class="admin-toern-summary-label">Zugeordnet (${ids.length}):</span> ${chips}`;
}

function selectedToernIdsFromContainer(container) {
  return [...container.querySelectorAll('input[type="checkbox"][data-toern-id]:checked')].map(
    (el) => Number(el.dataset.toernId)
  );
}

function fillToernChecklist(container, selectedIds, { disabled = false } = {}) {
  container.innerHTML = "";
  if (!allToerns.length) {
    container.innerHTML = '<p class="hint">Keine Törns geladen.</p>';
    return;
  }
  const set = new Set(selectedIds);
  const list = document.createElement("div");
  list.className = "admin-toern-checklist";
  allToerns.forEach((t) => {
    const id = `toern-cb-${container.closest("[data-id]")?.dataset.id || "new"}-${t.id}`;
    const label = document.createElement("label");
    label.className = "admin-toern-check";
    label.htmlFor = id;
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.id = id;
    cb.dataset.toernId = String(t.id);
    cb.checked = set.has(t.id);
    cb.disabled = disabled;
    const text = document.createElement("span");
    text.textContent = toernLabel(t);
    label.append(cb, text);
    list.appendChild(label);
  });
  container.appendChild(list);
}

function updateSummaryFromChecklist(card, user) {
  const summary = card.querySelector(".admin-toern-summary-wrap");
  const role = card.querySelector(".inp-role")?.value || user.role;
  const picker = card.querySelector(".admin-toern-picker");
  const hint = card.querySelector(".admin-toern-picker-hint");
  const isAdmin = role === "admin";
  if (hint) hint.hidden = !isAdmin;

  let ids = selectedToernIdsFromContainer(picker);
  if (!isAdmin && !ids.length) {
    ids = user.toernIds || [];
  }
  fillToernChecklist(picker, isAdmin ? [] : ids, { disabled: isAdmin });
  if (summary) {
    summary.innerHTML = toernSummaryInner({
      role,
      toernIds: isAdmin ? [] : ids,
    });
  }
}

function renderUsers() {
  if (!users.length) {
    userList.innerHTML = '<p class="hint">Noch keine Benutzer.</p>';
    return;
  }
  userList.innerHTML = users
    .map(
      (u) => `
    <article class="admin-user-card" data-id="${u.id}">
      <div class="admin-user-head">
        <div>
          <strong>${escapeHtml(u.username)}</strong>
          <span class="hint admin-role-badge">${u.role === "admin" ? "Admin" : "User"}</span>
        </div>
      </div>
      <div class="admin-toern-summary-wrap admin-toern-summary">${toernSummaryInner(u)}</div>
      <label class="field">
        <span>Neues Passwort (leer = unverändert)</span>
        <input type="password" class="inp-password" autocomplete="new-password" />
      </label>
      <label class="field">
        <span>Rolle</span>
        <select class="inp-role">
          <option value="user" ${u.role === "user" ? "selected" : ""}>User</option>
          <option value="admin" ${u.role === "admin" ? "selected" : ""}>Admin</option>
        </select>
      </label>
      <div class="field">
        <span>Törns zuordnen</span>
        <p class="hint admin-toern-picker-hint" ${u.role === "admin" ? "" : 'hidden'}>Admins haben Zugriff auf alle Törns; Zuordnung entfällt.</p>
        <div class="admin-toern-picker"></div>
      </div>
      <div class="photo-manage-actions">
        <button type="button" class="btn btn-save">Speichern</button>
        <button type="button" class="btn btn-danger btn-delete">Löschen</button>
      </div>
    </article>`
    )
    .join("");

  userList.querySelectorAll(".admin-user-card").forEach((card) => {
    const id = Number(card.dataset.id);
    const u = users.find((x) => x.id === id);
    if (!u) return;
    const picker = card.querySelector(".admin-toern-picker");
    fillToernChecklist(picker, u.toernIds || [], { disabled: u.role === "admin" });
    card.querySelector(".inp-role")?.addEventListener("change", () => updateSummaryFromChecklist(card, u));
    picker.addEventListener("change", () => updateSummaryFromChecklist(card, u));
  });
}

async function loadToerns() {
  allToerns = await fetchToerns();
  fillToernChecklist(newToerns, []);
}

async function loadUsers() {
  const res = await apiFetch("/api/admin/users");
  if (!res.ok) throw new Error("Benutzer konnten nicht geladen werden.");
  const data = await res.json();
  users = data.users || [];
  renderUsers();
}

createForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("newUsername").value.trim();
  const password = document.getElementById("newPassword").value;
  const role = document.getElementById("newRole").value;
  const toernIds = role === "admin" ? [] : selectedToernIdsFromContainer(newToerns);
  const res = await apiFetch("/api/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, role, toernIds }),
  });
  const data = await res.json();
  if (!res.ok) {
    showToast(data.error || "Anlegen fehlgeschlagen.");
    return;
  }
  createForm.reset();
  fillToernChecklist(newToerns, []);
  showToast(`Benutzer „${username}“ angelegt.`);
  await loadUsers();
});

userList.addEventListener("click", async (e) => {
  const card = e.target.closest(".admin-user-card");
  if (!card) return;
  const id = Number(card.dataset.id);
  if (e.target.closest(".btn-save")) {
    const password = card.querySelector(".inp-password")?.value ?? "";
    const role = card.querySelector(".inp-role")?.value;
    const toernIds =
      role === "admin" ? [] : selectedToernIdsFromContainer(card.querySelector(".admin-toern-picker"));
    const body = { role, toernIds };
    if (password) body.password = password;
    const res = await apiFetch(`/api/admin/users/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || "Speichern fehlgeschlagen.");
      return;
    }
    card.querySelector(".inp-password").value = "";
    showToast("Gespeichert.");
    await loadUsers();
  }
  if (e.target.closest(".btn-delete")) {
    const name = users.find((u) => u.id === id)?.username || id;
    if (!window.confirm(`Benutzer „${name}“ wirklich löschen?`)) return;
    const res = await apiFetch(`/api/admin/users/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || "Löschen fehlgeschlagen.");
      return;
    }
    showToast("Benutzer gelöscht.");
    await loadUsers();
  }
});

async function main() {
  if (!(await requireAdminOrRedirect())) return;
  try {
    await loadToerns();
    document.getElementById("newRole")?.addEventListener("change", (e) => {
      const isAdmin = e.target.value === "admin";
      fillToernChecklist(newToerns, [], { disabled: isAdmin });
    });
    await loadUsers();
  } catch (err) {
    showToast(err.message || "Fehler beim Laden");
  }
}

main();
