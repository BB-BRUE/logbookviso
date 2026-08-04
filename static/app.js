const STATUS = {
  0: { label: "Segeln", color: "#2f9e8a" },
  1: { label: "Festgemacht", color: "#6b7c8a" },
  2: { label: "Motor", color: "#d17a3a" },
  3: { label: "Anker", color: "#4a7fcb" },
};

const el = {
  select: document.getElementById("toernSelect"),
  meta: document.getElementById("toernMeta"),
  legend: document.getElementById("statusLegend"),
  count: document.getElementById("pointCount"),
  fit: document.getElementById("fitBtn"),
  card: document.getElementById("hoverCard"),
  toast: document.getElementById("toast"),
  mapWrap: document.querySelector(".map-wrap"),
  showPhotos: document.getElementById("showPhotos"),
  photoInfo: document.getElementById("photoInfo"),
  photoUpload: document.getElementById("photoUpload"),
  photoFiles: document.getElementById("photoFiles"),
  photoUploadBtn: document.getElementById("photoUploadBtn"),
};

let trackLayer = null;
let photoLayer = null;
let trackBounds = null;
let photoBounds = null;
let toastTimer = null;

const map = L.map("map", {
  zoomControl: true,
  worldCopyJump: true,
}).setView([44.5, 15.0], 7);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
}).addTo(map);

function statusInfo(code) {
  return STATUS[code] || { label: `Status ${code}`, color: "#9aa7b0" };
}

function fmt(value, unit = "") {
  if (value === null || value === undefined || value === "") return "—";
  return unit ? `${value} ${unit}` : String(value);
}

/** WGS84 Grad + Dezimalminuten, z. B. 53°54,2′ N / 007°53,8′ E */
function formatWgs84(lat, lon) {
  if (lat == null || lon == null) return { lat: "—", lon: "—" };

  const fmtHem = (value, pos, neg, degPad) => {
    const hemi = value >= 0 ? pos : neg;
    const abs = Math.abs(value);
    let deg = Math.floor(abs);
    let minutes = (abs - deg) * 60;
    // Rundung auf 1 Dezimalstelle (Komma)
    minutes = Math.round(minutes * 10) / 10;
    if (minutes >= 60) {
      minutes = 0;
      deg += 1;
    }
    const degStr = String(deg).padStart(degPad, "0");
    const minStr = minutes.toFixed(1).replace(".", ",");
    return `${degStr}°${minStr}′ ${hemi}`;
  };

  return {
    lat: fmtHem(lat, "N", "S", 2),
    lon: fmtHem(lon, "E", "W", 3),
  };
}

function renderLegend() {
  el.legend.innerHTML = Object.entries(STATUS)
    .map(
      ([code, info]) => `
      <li>
        <span class="swatch" style="background:${info.color}"></span>
        <span>${info.label} <small style="opacity:.65">(${code})</small></span>
      </li>`
    )
    .join("");
}

function showToast(message) {
  el.toast.hidden = false;
  el.toast.textContent = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.toast.hidden = true;
  }, 3200);
}

function renderMeta(toern) {
  if (!toern) {
    el.meta.hidden = true;
    return;
  }
  const parts = [
    toern.ship ? `<div class="row">Schiff: ${escapeHtml(toern.ship)}</div>` : "",
    toern.revier ? `<div class="row">Revier: ${escapeHtml(toern.revier)}</div>` : "",
    toern.from || toern.to
      ? `<div class="row">${escapeHtml(toern.from || "?")} → ${escapeHtml(toern.to || "?")}</div>`
      : "",
  ].filter(Boolean);

  el.meta.hidden = false;
  el.meta.innerHTML = `<strong>${escapeHtml(toern.name)}</strong>${parts.join("")}`;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function popupHtml(p) {
  const st = statusInfo(p.status);
  const wgs = formatWgs84(p.lat, p.lon);
  return `
    <h3>
      <span class="badge" style="background:${st.color}33;color:${st.color}">${escapeHtml(st.label)}</span>
      ${p.recordtype === 1 ? '<span class="badge">Manuell</span>' : ""}
    </h3>
    <dl class="hover-grid">
      <dt>Time</dt><dd>${escapeHtml(fmt(p.time))}</dd>
      <dt>COG</dt><dd>${escapeHtml(fmt(p.cog, "°"))}</dd>
      <dt>LAT</dt><dd>${escapeHtml(wgs.lat)}</dd>
      <dt>LON</dt><dd>${escapeHtml(wgs.lon)}</dd>
      <dt>SOG</dt><dd>${escapeHtml(fmt(p.sog, "kn"))}</dd>
      <dt>M/H</dt><dd>${escapeHtml(fmt(p.engineHrs, "h"))}</dd>
      <dt>LOG</dt><dd>${escapeHtml(fmt(p.log, "sm"))}</dd>
      <dt>GEO</dt><dd>${escapeHtml(fmt(p.geo))}</dd>
      <dt>Text</dt><dd>${escapeHtml(fmt(p.text))}</dd>
      <div class="section">Wetterdaten</div>
      <dt>Luftdruck</dt><dd>${escapeHtml(fmt(p.pressure, "hPa"))}</dd>
      <dt>Wind TWS</dt><dd>${escapeHtml(fmt(p.windTws, "kn"))}</dd>
      <dt>Wind TWD</dt><dd>${escapeHtml(fmt(p.windTwd, "°"))}</dd>
      <dt>Böen</dt><dd>${escapeHtml(fmt(p.windGusts, "kn"))}</dd>
      <dt>Welle</dt><dd>${escapeHtml(fmt(p.wave, "m"))}</dd>
    </dl>
  `;
}

function placeCard(latlng) {
  const point = map.latLngToContainerPoint(latlng);
  const card = el.card;
  const pad = 14;
  const w = card.offsetWidth || 300;
  const h = card.offsetHeight || 280;
  const maxW = el.mapWrap.clientWidth;
  const maxH = el.mapWrap.clientHeight;

  let left = point.x + 16;
  let top = point.y - 20;

  if (left + w + pad > maxW) left = point.x - w - 16;
  if (left < pad) left = pad;
  if (top + h + pad > maxH) top = maxH - h - pad;
  if (top < pad) top = pad;

  card.style.left = `${left}px`;
  card.style.top = `${top}px`;
}

function clearPhotos() {
  if (photoLayer) {
    map.removeLayer(photoLayer);
    photoLayer = null;
  }
  photoBounds = null;
  if (el.photoInfo) el.photoInfo.textContent = "Fotos: —";
}

function photoPopupHtml(cluster) {
  const items = cluster.photos
    .map((p) => {
      const title = p.title ? escapeHtml(p.title) : "Foto";
      return `<a href="${escapeHtml(p.url)}" target="_blank" rel="noopener noreferrer" title="${title}">
        <img src="${escapeHtml(p.thumbUrl)}" alt="${title}" loading="lazy" />
      </a>`;
    })
    .join("");
  return `<div class="photo-popup"><h4>${cluster.count} Foto${cluster.count === 1 ? "" : "s"}</h4><div class="photo-grid">${items}</div></div>`;
}

function drawPhotoClusters(clusters) {
  clearPhotos();
  if (!el.showPhotos?.checked || !clusters.length) {
    if (el.photoInfo) {
      el.photoInfo.textContent = clusters.length
        ? "Fotos: ausgeblendet"
        : "Fotos: keine Marker";
    }
    return;
  }

  photoLayer = L.layerGroup().addTo(map);
  const latlngs = [];

  clusters.forEach((cluster) => {
    latlngs.push([cluster.lat, cluster.lon]);
    const icon = L.divIcon({
      className: "",
      html: `<div class="photo-marker" title="Fotos">${cluster.count}</div>`,
      iconSize: [26, 26],
      iconAnchor: [13, 13],
    });
    const marker = L.marker([cluster.lat, cluster.lon], { icon });
    marker.bindPopup(photoPopupHtml(cluster), {
      className: "photo-popup-wrap",
      maxWidth: 660,
      minWidth: 300,
    });
    marker.addTo(photoLayer);
  });

  photoBounds = L.latLngBounds(latlngs);
  if (el.photoInfo) {
    const total = clusters.reduce((n, c) => n + c.count, 0);
    el.photoInfo.textContent = `Fotos: ${total} Bilder, ${clusters.length} Marker`;
  }
}

function fitMapBounds() {
  const boundsList = [];
  if (trackBounds) boundsList.push(trackBounds);
  if (photoBounds && el.showPhotos?.checked) boundsList.push(photoBounds);
  if (!boundsList.length) return;
  let bounds = boundsList[0];
  for (let i = 1; i < boundsList.length; i += 1) {
    bounds = bounds.extend(boundsList[i]);
  }
  map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
}

function clearTrack() {
  if (trackLayer) {
    map.removeLayer(trackLayer);
    trackLayer = null;
  }
  trackBounds = null;
  clearPhotos();
  el.card.hidden = true;
  el.fit.disabled = true;
  el.count.textContent = "—";
}

function drawTrack(points) {
  clearTrack();

  if (!points.length) {
    el.count.textContent = "0 Punkte";
    showToast("Keine Koordinaten für diesen Törn.");
    return;
  }

  trackLayer = L.layerGroup().addTo(map);
  const latlngs = points.map((p) => [p.lat, p.lon]);

  // Segmented polyline by status for visual continuity
  let segment = [latlngs[0]];
  let currentStatus = points[0].status;

  const flush = () => {
    if (segment.length < 2) return;
    L.polyline(segment, {
      color: statusInfo(currentStatus).color,
      weight: 3.5,
      opacity: 0.85,
      lineJoin: "round",
      lineCap: "round",
    }).addTo(trackLayer);
  };

  for (let i = 1; i < points.length; i += 1) {
    const p = points[i];
    if (p.status !== currentStatus) {
      segment.push(latlngs[i]);
      flush();
      currentStatus = p.status;
      segment = [latlngs[i]];
    } else {
      segment.push(latlngs[i]);
    }
  }
  flush();

  points.forEach((p) => {
    const major = p.recordtype === 1;
    const size = major ? 12 : 7;
    const color = statusInfo(p.status).color;
    const marker = L.circleMarker([p.lat, p.lon], {
      radius: size / 2,
      color: "#ffffff",
      weight: major ? 2.5 : 1.5,
      fillColor: color,
      fillOpacity: 0.95,
      className: major ? "track-dot is-major" : "track-dot",
    });

    marker.on("mouseover", (e) => {
      el.card.hidden = false;
      el.card.innerHTML = popupHtml(p);
      placeCard(e.latlng);
      marker.setStyle({
        radius: (size / 2) + 2,
        weight: major ? 3 : 2,
      });
    });

    marker.on("mousemove", (e) => placeCard(e.latlng));

    marker.on("mouseout", () => {
      el.card.hidden = true;
      marker.setStyle({
        radius: size / 2,
        weight: major ? 2.5 : 1.5,
      });
    });

    marker.addTo(trackLayer);
  });

  trackBounds = L.latLngBounds(latlngs);
  fitMapBounds();
  el.fit.disabled = false;
  el.count.textContent = `${points.length.toLocaleString("de-DE")} Punkte`;
}

async function uploadPhotos(toernId) {
  const files = el.photoFiles?.files;
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
  for (const file of files) {
    form.append("photos", file);
  }

  el.photoUploadBtn.disabled = true;
  try {
    const res = await fetch("/api/photos/upload", { method: "POST", body: form });
    let data = {};
    try {
      data = await res.json();
    } catch {
      if (res.status === 413) {
        throw new Error("Upload zu groß – weniger Dateien auf einmal wählen.");
      }
      throw new Error(`Upload fehlgeschlagen (HTTP ${res.status}).`);
    }
    if (!res.ok) {
      throw new Error(data.error || "Upload fehlgeschlagen.");
    }
    if (data.errors?.length) {
      showToast(`${data.count} gespeichert, ${data.errors.length} Fehler`);
    } else {
      showToast(`${data.count} Foto(s) hochgeladen.`);
    }
    el.photoUpload?.reset();
    await loadPhotos(toernId);
    fitMapBounds();
  } catch (err) {
    showToast(err.message || "Upload fehlgeschlagen");
  } finally {
    el.photoUploadBtn.disabled = false;
  }
}

async function loadPhotos(toernId) {
  if (!el.showPhotos?.checked) {
    clearPhotos();
    if (el.photoInfo) el.photoInfo.textContent = "Fotos: ausgeblendet";
    return;
  }
  try {
    const res = await fetch(`/api/photos/${toernId}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "Fotos konnten nicht geladen werden.");
    }
    const data = await res.json();
    drawPhotoClusters(data.clusters || []);
    if (data.warnings?.length) {
      showToast(data.warnings[0]);
    }
    if (trackBounds || photoBounds) fitMapBounds();
  } catch (err) {
    clearPhotos();
    if (el.photoInfo) el.photoInfo.textContent = "Fotos: Fehler";
    showToast(err.message || "Fotos nicht verfügbar");
  }
}

async function loadToerns() {
  const res = await fetch("/api/toerns");
  if (!res.ok) throw new Error("Törns konnten nicht geladen werden.");
  const toerns = await res.json();

  el.select.innerHTML = "";
  const usable = toerns.filter((t) => t.pointsWithCoords > 0);
  const empty = toerns.filter((t) => t.pointsWithCoords === 0);

  if (!usable.length) {
    el.select.innerHTML = "<option>Keine Tracks mit Koordinaten</option>";
    showToast("Keine Törns mit GPS-Daten gefunden.");
    return [];
  }

  usable.forEach((t) => {
    const opt = document.createElement("option");
    opt.value = String(t.id);
    opt.textContent = `${t.name} (${t.pointsWithCoords} Pts)`;
    el.select.appendChild(opt);
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
    el.select.appendChild(group);
  }

  el.select.disabled = false;
  return toerns;
}

async function loadTrack(toernId, toerns) {
  el.count.textContent = "Lade…";
  const res = await fetch(`/api/track/${toernId}`);
  if (!res.ok) throw new Error("Track konnte nicht geladen werden.");
  const data = await res.json();
  const toern = toerns.find((t) => t.id === Number(toernId));
  renderMeta(toern);
  drawTrack(data.points);
  await loadPhotos(toernId);
}

async function main() {
  renderLegend();
  el.fit.addEventListener("click", () => fitMapBounds());
  el.showPhotos?.addEventListener("change", async () => {
    const id = Number(el.select.value);
    if (!Number.isFinite(id)) return;
    await loadPhotos(id);
    fitMapBounds();
  });

  el.photoUpload?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = Number(el.select.value);
    if (!Number.isFinite(id)) {
      showToast("Bitte zuerst einen Törn wählen.");
      return;
    }
    await uploadPhotos(id);
  });

  try {
    const toerns = await loadToerns();
    if (!toerns.length) return;

    const first = toerns.find((t) => t.pointsWithCoords > 0);
    if (first) {
      el.select.value = String(first.id);
      await loadTrack(first.id, toerns);
    }

    el.select.addEventListener("change", async () => {
      const id = Number(el.select.value);
      try {
        await loadTrack(id, toerns);
      } catch (err) {
        showToast(err.message || "Fehler beim Laden");
      }
    });
  } catch (err) {
    showToast(err.message || "Server nicht erreichbar");
    el.select.innerHTML = "<option>Fehler beim Laden</option>";
  }
}

main();
