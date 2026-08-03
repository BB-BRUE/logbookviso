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
};

let trackLayer = null;
let trackBounds = null;
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

function clearTrack() {
  if (trackLayer) {
    map.removeLayer(trackLayer);
    trackLayer = null;
  }
  trackBounds = null;
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
  map.fitBounds(trackBounds, { padding: [40, 40], maxZoom: 14 });
  el.fit.disabled = false;
  el.count.textContent = `${points.length.toLocaleString("de-DE")} Punkte`;
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
}

async function main() {
  renderLegend();
  el.fit.addEventListener("click", () => {
    if (trackBounds) map.fitBounds(trackBounds, { padding: [40, 40], maxZoom: 14 });
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
