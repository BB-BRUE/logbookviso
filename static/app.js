const STATUS = {
  0: { label: "Segeln", color: "#2f9e8a" },
  1: { label: "Festgemacht", color: "#6b7c8a" },
  2: { label: "Motor", color: "#d17a3a" },
  3: { label: "Anker", color: "#4a7fcb" },
};

/** Abstand der Wetter-Symbole entlang des Logs (Seemeilen) */
const WEATHER_INTERVAL_SM = 15;
const WEATHER_WINDOW_SM = WEATHER_INTERVAL_SM / 2;
/** Versatz der Wetter-Symbole quer zum Track (Meter) */
const WEATHER_OFFSET_M = 320;

const MOBILE_SIDEBAR_MQ = window.matchMedia("(max-width: 860px)");
const SIDEBAR_OPEN_KEY = "logbookviso.sidebarOpen";

const el = {
  app: document.getElementById("app"),
  sidebarToggle: document.getElementById("sidebarToggle"),
  sidebarClose: document.getElementById("sidebarClose"),
  sidebarBackdrop: document.getElementById("sidebarBackdrop"),
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
  managePhotosLink: document.getElementById("managePhotosLink"),
  navAdmin: document.getElementById("navAdmin"),
  navLogbook: document.getElementById("navLogbook"),
  slideshowBtn: document.getElementById("slideshowBtn"),
  showUnlocatedOnly: document.getElementById("showUnlocatedOnly"),
  unlocatedList: document.getElementById("unlocatedList"),
  userBar: document.getElementById("userBar"),
  userName: document.getElementById("userName"),
  logoutBtn: document.getElementById("logoutBtn"),
};

let trackLayer = null;
let photoLayer = null;
let trackBounds = null;
let photoBounds = null;
let lightboxPhotos = [];
let lightboxIndex = 0;
let hoverHideTimer = null;
let activeTrackMarker = null;
let lastPhotoPayload = null;
let currentToernId = null;

const lightbox = {
  root: null,
  main: null,
  caption: null,
  strip: null,
  close: null,
  prev: null,
  next: null,
  video: null,
};

const map = L.map("map", {
  zoomControl: true,
  worldCopyJump: true,
}).setView([44.5, 15.0], 7);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
}).addTo(map);

L.tileLayer("https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution:
    '&copy; <a href="https://www.openseamap.org/">OpenSeaMap</a> contributors',
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

function clearHoverHideTimer() {
  if (hoverHideTimer) {
    clearTimeout(hoverHideTimer);
    hoverHideTimer = null;
  }
}

function resetActiveTrackMarker() {
  if (activeTrackMarker) {
    const node = activeTrackMarker.getElement();
    if (node) node.classList.remove("is-active");
    activeTrackMarker = null;
  }
}

function hideHoverCard() {
  clearHoverHideTimer();
  el.card.hidden = true;
  resetActiveTrackMarker();
}

function scheduleHideHoverCard() {
  clearHoverHideTimer();
  hoverHideTimer = setTimeout(hideHoverCard, 280);
}

function highlightTrackMarker(marker) {
  resetActiveTrackMarker();
  activeTrackMarker = marker;
  const node = marker.getElement();
  if (node) node.classList.add("is-active");
}

/** Kurs über Grund in Grad (0 = Nord). Fallback: Richtung zum nächsten/vorherigen Punkt. */
function courseForPoint(points, index) {
  const cog = points[index].cog;
  if (cog != null && Number.isFinite(Number(cog)) && Number(cog) >= 0) {
    return ((Number(cog) % 360) + 360) % 360;
  }
  const cur = points[index];
  const next = points[index + 1];
  if (next) return bearingDeg(cur.lat, cur.lon, next.lat, next.lon);
  const prev = points[index - 1];
  if (prev) return bearingDeg(prev.lat, prev.lon, cur.lat, cur.lon);
  return 0;
}

function bearingDeg(lat1, lon1, lat2, lon2) {
  const φ1 = (lat1 * Math.PI) / 180;
  const φ2 = (lat2 * Math.PI) / 180;
  const Δλ = ((lon2 - lon1) * Math.PI) / 180;
  const y = Math.sin(Δλ) * Math.cos(φ2);
  const x =
    Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

function trackArrowIcon(color, size, courseDeg, major) {
  const half = size / 2;
  const stroke = major ? 2 : 1.5;
  return L.divIcon({
    className: major ? "track-arrow-wrap is-major" : "track-arrow-wrap",
    html: `<div class="track-arrow" style="--course:${courseDeg}deg;--arrow:${color};width:${size}px;height:${size}px">
      <svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true">
        <path d="M12 2.5 L20.5 20.5 L12 15.5 L3.5 20.5 Z"
          fill="${color}" stroke="#fff" stroke-width="${stroke}"
          stroke-linejoin="round"/>
      </svg>
    </div>`,
    iconSize: [size, size],
    iconAnchor: [half, half],
  });
}

function avgNum(values) {
  const nums = values
    .filter((v) => v != null && Number.isFinite(Number(v)))
    .map(Number);
  if (!nums.length) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

/** Windrichtung (FROM) als gewichtetes Kreis-Mittel; Gewicht = Windgeschwindigkeit. */
function avgWindDir(points) {
  let sinSum = 0;
  let cosSum = 0;
  let wSum = 0;
  for (const p of points) {
    if (p.windTwd == null || !Number.isFinite(Number(p.windTwd))) continue;
    if (Number(p.windTwd) < 0) continue;
    const w =
      p.windTws != null && Number.isFinite(Number(p.windTws)) && Number(p.windTws) > 0
        ? Number(p.windTws)
        : 1;
    const r = (Number(p.windTwd) * Math.PI) / 180;
    sinSum += w * Math.sin(r);
    cosSum += w * Math.cos(r);
    wSum += w;
  }
  if (!wSum) return null;
  return ((Math.atan2(sinSum, cosSum) * 180) / Math.PI + 360) % 360;
}

function round1(n) {
  return n == null ? null : Math.round(n * 10) / 10;
}

/** Punkt um distanceM Meter in Richtung bearingDeg (0 = Nord) verschieben. */
function offsetLatLon(lat, lon, bearingDeg, distanceM) {
  const R = 6371000;
  const δ = distanceM / R;
  const θ = (bearingDeg * Math.PI) / 180;
  const φ1 = (lat * Math.PI) / 180;
  const λ1 = (lon * Math.PI) / 180;
  const sinφ1 = Math.sin(φ1);
  const cosφ1 = Math.cos(φ1);
  const sinδ = Math.sin(δ);
  const cosδ = Math.cos(δ);
  const φ2 = Math.asin(sinφ1 * cosδ + cosφ1 * sinδ * Math.cos(θ));
  const λ2 =
    λ1 +
    Math.atan2(Math.sin(θ) * sinδ * cosφ1, cosδ - sinφ1 * Math.sin(φ2));
  return [(φ2 * 180) / Math.PI, (((λ2 * 180) / Math.PI + 540) % 360) - 180];
}

function courseAtLoggedIndex(logged, index) {
  const p = logged[index];
  if (p.cog != null && Number.isFinite(Number(p.cog)) && Number(p.cog) >= 0) {
    return ((Number(p.cog) % 360) + 360) % 360;
  }
  const next = logged[index + 1];
  if (next) return bearingDeg(p.lat, p.lon, next.lat, next.lon);
  const prev = logged[index - 1];
  if (prev) return bearingDeg(prev.lat, prev.lon, p.lat, p.lon);
  return 0;
}

function fmtShortTime(ts) {
  if (ts == null) return "—";
  try {
    return (
      new Date(ts).toLocaleString("de-DE", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "UTC",
      }) + " UTC"
    );
  } catch {
    return "—";
  }
}

/**
 * Wind-Samples alle WEATHER_INTERVAL_SM laut Logge; Mittelwerte aus Punkten ± Fenster.
 * Position = nächster Track-Punkt zum Sample-Log.
 */
function buildWeatherSamples(points) {
  const logged = points.filter(
    (p) => p.log != null && Number.isFinite(Number(p.log))
  );
  if (!logged.length) return [];

  const logStart = Number(logged[0].log);
  const logEnd = Number(logged[logged.length - 1].log);
  if (!(logEnd > logStart)) return [];

  const samples = [];

  for (
    let target = logStart;
    target <= logEnd;
    target += WEATHER_INTERVAL_SM
  ) {
    let nearestIdx = 0;
    let bestD = Math.abs(Number(logged[0].log) - target);
    for (let i = 1; i < logged.length; i += 1) {
      const d = Math.abs(Number(logged[i].log) - target);
      if (d < bestD) {
        bestD = d;
        nearestIdx = i;
      }
    }
    const nearest = logged[nearestIdx];

    const window = logged.filter(
      (p) => Math.abs(Number(p.log) - target) <= WEATHER_WINDOW_SM
    );
    const pool = window.length ? window : [nearest];

    const pressure = round1(avgNum(pool.map((p) => p.pressure)));
    const wave = round1(avgNum(pool.map((p) => p.wave)));
    const windTws = round1(avgNum(pool.map((p) => p.windTws)));
    const windGusts = round1(avgNum(pool.map((p) => p.windGusts)));
    const windTwdRaw = avgWindDir(pool);
    const windTwd = windTwdRaw == null ? null : Math.round(windTwdRaw);

    if (windTws == null && windTwd == null) continue;

    const course = courseAtLoggedIndex(logged, nearestIdx);
    const [offLat, offLon] = offsetLatLon(
      nearest.lat,
      nearest.lon,
      course - 90,
      WEATHER_OFFSET_M
    );

    samples.push({
      lat: nearest.lat,
      lon: nearest.lon,
      markerLat: offLat,
      markerLon: offLon,
      course,
      ts: nearest.ts != null ? Number(nearest.ts) : null,
      time: nearest.time || fmtShortTime(nearest.ts),
      log: round1(Number(nearest.log)),
      targetLog: round1(target),
      pressure,
      wave,
      windTws,
      windTwd,
      windGusts,
      sampleCount: pool.length,
    });
  }

  return samples;
}

function weatherPopupHtml(s) {
  return `
    <h3>
      <span class="badge" style="background:rgba(74,127,203,0.25);color:#8eb6e8">Wetter</span>
      Ø ${s.sampleCount} Punkte (±${WEATHER_WINDOW_SM} sm)
    </h3>
    <dl class="hover-grid">
      <dt>Zeit</dt><dd>${escapeHtml(fmt(s.time))}</dd>
      <dt>LOG</dt><dd>${escapeHtml(fmt(s.log, "sm"))}</dd>
      <div class="section">Mittelwerte</div>
      <dt>Luftdruck</dt><dd>${escapeHtml(fmt(s.pressure, "hPa"))}</dd>
      <dt>Wind TWS</dt><dd>${escapeHtml(fmt(s.windTws, "kn"))}</dd>
      <dt>Wind TWD</dt><dd>${escapeHtml(fmt(s.windTwd, "°"))}</dd>
      <dt>Böen</dt><dd>${escapeHtml(fmt(s.windGusts, "kn"))}</dd>
      <dt>Welle</dt><dd>${escapeHtml(fmt(s.wave, "m"))}</dd>
    </dl>
  `;
}

function weatherIcon(sample) {
  const twd = sample.windTwd != null ? sample.windTwd : 0;
  const speed =
    sample.windTws != null ? fmt(sample.windTws, "kn") : fmt(sample.windTwd, "°");
  const w = 72;
  const h = 36;
  return L.divIcon({
    className: "weather-marker-wrap",
    html: `<div class="weather-marker">
      <div class="wm-wind">
        <svg class="wm-arrow" style="--twd:${twd}deg" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path d="M12 3 L12 17 M12 3 L7 9 M12 3 L17 9" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <span>${escapeHtml(speed)}</span>
      </div>
    </div>`,
    iconSize: [w, h],
    iconAnchor: [w / 2, h / 2],
  });
}

function drawWeatherSamples(points) {
  const samples = buildWeatherSamples(points);

  samples.forEach((s) => {
    L.polyline(
      [
        [s.lat, s.lon],
        [s.markerLat, s.markerLon],
      ],
      {
        color: "rgba(142, 182, 232, 0.55)",
        weight: 1.25,
        dashArray: "3 5",
        opacity: 0.9,
        interactive: false,
        className: "weather-leader",
      }
    ).addTo(trackLayer);

    const marker = L.marker([s.markerLat, s.markerLon], {
      icon: weatherIcon(s),
      interactive: true,
      keyboard: false,
      zIndexOffset: 500,
    });

    marker.on("mouseover", (e) => {
      clearHoverHideTimer();
      resetActiveTrackMarker();
      el.card.hidden = false;
      el.card.innerHTML = weatherPopupHtml(s);
      placeCard(e.latlng);
    });
    marker.on("mousemove", (e) => placeCard(e.latlng));
    marker.on("mouseout", () => scheduleHideHoverCard());
    marker.addTo(trackLayer);
  });
}

function initPhotoLightbox() {
  lightbox.root = document.getElementById("photoLightbox");
  lightbox.main = document.getElementById("photoLightboxMain");
  lightbox.caption = document.getElementById("photoLightboxCaption");
  lightbox.strip = document.getElementById("photoLightboxStrip");
  lightbox.close = document.getElementById("photoLightboxClose");
  lightbox.prev = document.getElementById("photoLightboxPrev");
  lightbox.next = document.getElementById("photoLightboxNext");
  lightbox.video = document.getElementById("photoLightboxVideo");
  if (!lightbox.root) return;

  lightbox.close.addEventListener("click", closePhotoLightbox);
  lightbox.root.addEventListener("click", (e) => {
    if (e.target === lightbox.root) closePhotoLightbox();
  });
  lightbox.prev.addEventListener("click", () => stepLightbox(-1));
  lightbox.next.addEventListener("click", () => stepLightbox(1));
  lightbox.strip.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-index]");
    if (!btn) return;
    setLightboxIndex(Number(btn.dataset.index));
  });

  document.addEventListener("keydown", (e) => {
    if (lightbox.root.hidden) return;
    if (e.key === "Escape") closePhotoLightbox();
    if (e.key === "ArrowLeft") stepLightbox(-1);
    if (e.key === "ArrowRight") stepLightbox(1);
  });
}

function renderLightboxStrip() {
  lightbox.strip.innerHTML = lightboxPhotos
    .map((p, i) => {
      const title = escapeHtml(p.title || "Foto");
      const active = i === lightboxIndex ? " is-active" : "";
      return `<button type="button" class="photo-lightbox-thumb${active}" data-index="${i}" title="${title}">
        <img src="${escapeHtml(p.thumbUrl)}" alt="" loading="lazy" />
      </button>`;
    })
    .join("");
  const activeThumb = lightbox.strip.querySelector(".is-active");
  activeThumb?.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
}

function setLightboxIndex(index) {
  if (!lightboxPhotos.length) return;
  lightboxIndex = (index + lightboxPhotos.length) % lightboxPhotos.length;
  const p = lightboxPhotos[lightboxIndex];
  const isVideo = Boolean(p.isVideo);
  if (isVideo && lightbox.video) {
    lightbox.main.hidden = true;
    lightbox.main.removeAttribute("src");
    lightbox.video.hidden = false;
    lightbox.video.src = p.url;
    lightbox.video.load();
  } else {
    if (lightbox.video) {
      lightbox.video.hidden = true;
      lightbox.video.pause();
      lightbox.video.removeAttribute("src");
    }
    lightbox.main.hidden = false;
    lightbox.main.src = p.url;
    lightbox.main.alt = p.title || "Foto";
  }
  const n = lightboxPhotos.length;
  const kind = isVideo ? "Video" : "Foto";
  lightbox.caption.textContent = `${p.title || kind} (${lightboxIndex + 1} / ${n})`;
  lightbox.prev.hidden = n <= 1;
  lightbox.next.hidden = n <= 1;
  renderLightboxStrip();
}

function stepLightbox(delta) {
  setLightboxIndex(lightboxIndex + delta);
}

function openPhotoLightbox(cluster, startIndex = 0) {
  if (!lightbox.root || !cluster?.photos?.length) return;
  lightboxPhotos = cluster.photos;
  lightbox.root.hidden = false;
  document.body.classList.add("lightbox-open");
  setLightboxIndex(Math.min(startIndex, lightboxPhotos.length - 1));
}

function closePhotoLightbox() {
  if (!lightbox.root) return;
  lightbox.root.hidden = true;
  document.body.classList.remove("lightbox-open");
  lightbox.main.removeAttribute("src");
  lightbox.main.hidden = false;
  if (lightbox.video) {
    lightbox.video.pause();
    lightbox.video.removeAttribute("src");
    lightbox.video.hidden = true;
  }
  lightboxPhotos = [];
}

function clearPhotos() {
  if (photoLayer) {
    map.removeLayer(photoLayer);
    photoLayer = null;
  }
  photoBounds = null;
  if (el.photoInfo) el.photoInfo.textContent = "Fotos: —";
}

function openPhotoSlideshow(photos, startIndex = 0) {
  if (!photos?.length) {
    showToast("Keine Medien für diesen Törn.");
    return;
  }
  openPhotoLightbox({ photos }, startIndex);
}

function renderUnlocatedList(items) {
  if (!el.unlocatedList) return;
  if (!items.length) {
    el.unlocatedList.hidden = true;
    el.unlocatedList.innerHTML = "";
    return;
  }
  el.unlocatedList.hidden = false;
  el.unlocatedList.innerHTML = items
    .map(
      (p, i) =>
        `<li><button type="button" class="unlocated-item" data-index="${i}">${escapeHtml(p.title || `#${p.id}`)}</button></li>`
    )
    .join("");
  el.unlocatedList.querySelectorAll(".unlocated-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.dataset.index);
      const list = lastPhotoPayload?.unlocatedOnlyList || [];
      openPhotoSlideshow(list, idx);
    });
  });
}

function applyPhotoView(data) {
  lastPhotoPayload = data;
  const unlocatedOnly = Boolean(el.showUnlocatedOnly?.checked);
  const clusters = unlocatedOnly ? [] : data.clusters || [];
  const unlocated = data.unlocated || [];

  if (unlocatedOnly) {
    drawPhotoClusters([]);
    lastPhotoPayload.unlocatedOnlyList = unlocated;
    renderUnlocatedList(unlocated);
    if (el.photoInfo) {
      el.photoInfo.textContent = `${unlocated.length} ohne Koordinaten`;
    }
  } else {
    renderUnlocatedList([]);
    if (el.unlocatedList) el.unlocatedList.hidden = true;
    drawPhotoClusters(clusters);
    if (el.photoInfo && data.meta) {
      const u = data.meta.unlocatedCount || 0;
      const extra = u ? ` · ${u} ohne GPS` : "";
      el.photoInfo.textContent = `Medien: ${data.meta.photoCount || 0}${extra}`;
    }
  }
  if (el.slideshowBtn) {
    el.slideshowBtn.disabled = !(data.slideshow?.length);
  }
}

function drawPhotoClusters(clusters) {
  clearPhotos();
  closePhotoLightbox();
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
    marker.on("click", () => openPhotoLightbox(cluster, 0));
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
  resetActiveTrackMarker();
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

  points.forEach((p, i) => {
    const major = p.recordtype === 1;
    const size = major ? 18 : 12;
    const color = statusInfo(p.status).color;
    const course = courseForPoint(points, i);
    const marker = L.marker([p.lat, p.lon], {
      icon: trackArrowIcon(color, size, course, major),
      interactive: true,
      keyboard: false,
    });

    marker.on("mouseover", (e) => {
      clearHoverHideTimer();
      el.card.hidden = false;
      el.card.innerHTML = popupHtml(p);
      placeCard(e.latlng);
      highlightTrackMarker(marker);
    });

    marker.on("mousemove", (e) => placeCard(e.latlng));

    marker.on("mouseout", () => {
      scheduleHideHoverCard();
    });

    marker.addTo(trackLayer);
  });

  drawWeatherSamples(points);

  trackBounds = L.latLngBounds(latlngs);
  fitMapBounds();
  el.fit.disabled = false;
  el.count.textContent = `${points.length.toLocaleString("de-DE")} Punkte`;
}

function syncManagePhotosLink(toernId) {
  if (!el.managePhotosLink) return;
  el.managePhotosLink.href = Number.isFinite(toernId)
    ? `/photos?toern=${toernId}`
    : "/photos";
}

async function loadPhotos(toernId) {
  currentToernId = toernId;
  try {
    const res = await apiFetch(`/api/photos/${toernId}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || "Medien konnten nicht geladen werden.");
    }
    const data = await res.json();
    lastPhotoPayload = data;
    if (!el.showPhotos?.checked && !el.showUnlocatedOnly?.checked) {
      clearPhotos();
      if (el.photoInfo) el.photoInfo.textContent = "Medien: ausgeblendet (Diashow möglich)";
      if (el.slideshowBtn) el.slideshowBtn.disabled = !(data.slideshow?.length);
      return;
    }
    applyPhotoView(data);
    if (data.warnings?.length) {
      showToast(data.warnings[0]);
    }
    if (trackBounds || photoBounds) fitMapBounds();
  } catch (err) {
    clearPhotos();
    lastPhotoPayload = null;
    if (el.photoInfo) el.photoInfo.textContent = "Medien: Fehler";
    if (el.slideshowBtn) el.slideshowBtn.disabled = true;
    showToast(err.message || "Medien nicht verfügbar");
  }
}

async function loadToerns() {
  const toerns = await fetchToerns();
  const { hasUsable } = fillToernSelect(el.select, toerns, "map");
  if (!hasUsable) {
    showToast("Keine Törns mit GPS-Daten gefunden.", { duration: 3200 });
    return [];
  }
  return toerns;
}

async function loadTrack(toernId, toerns) {
  el.count.textContent = "Lade…";
  const res = await apiFetch(`/api/track/${toernId}`);
  if (!res.ok) throw new Error("Track konnte nicht geladen werden.");
  const data = await res.json();
  const toern = toerns.find((t) => t.id === Number(toernId));
  renderMeta(toern);
  syncManagePhotosLink(Number(toernId));
  drawTrack(data.points);
  await loadPhotos(toernId);
}

async function main() {
  renderLegend();
  initPhotoLightbox();
  el.card.addEventListener("mouseenter", () => clearHoverHideTimer());
  el.card.addEventListener("mouseleave", () => scheduleHideHoverCard());
  el.fit.addEventListener("click", () => fitMapBounds());
  el.showPhotos?.addEventListener("change", async () => {
    const id = Number(el.select.value);
    if (!Number.isFinite(id)) return;
    await loadPhotos(id);
    fitMapBounds();
  });
  el.showUnlocatedOnly?.addEventListener("change", async () => {
    if (lastPhotoPayload) {
      applyPhotoView(lastPhotoPayload);
    } else if (currentToernId != null) {
      await loadPhotos(currentToernId);
    }
  });
  el.slideshowBtn?.addEventListener("click", () => {
    openPhotoSlideshow(lastPhotoPayload?.slideshow || [], 0);
  });

  try {
    const me = await loadCurrentUser();
    if (me) {
      el.userBar.hidden = false;
      el.userName.textContent = me.username;
      if (me.isAdmin) {
        if (el.navAdmin) el.navAdmin.hidden = false;
        if (el.navLogbook) el.navLogbook.hidden = false;
      }
    }
    el.logoutBtn?.addEventListener("click", () => logout());
  } catch {
    return;
  }

  try {
    const toerns = await loadToerns();
    if (!toerns.length) return;

    const first = toerns.find((t) => t.pointsWithCoords > 0);
    const params = new URLSearchParams(window.location.search);
    const toernFromUrl = params.get("toern");
    const pick =
      toernFromUrl && toerns.some((t) => String(t.id) === toernFromUrl)
        ? toerns.find((t) => String(t.id) === toernFromUrl)
        : first;
    if (pick) {
      el.select.value = String(pick.id);
      await loadTrack(pick.id, toerns);
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

function sidebarIsMobile() {
  return MOBILE_SIDEBAR_MQ.matches;
}

function setSidebarOpen(open) {
  if (!el.app) return;
  el.app.classList.toggle("sidebar-collapsed", !open);
  if (el.sidebarToggle) {
    el.sidebarToggle.hidden = open;
    el.sidebarToggle.setAttribute("aria-expanded", open ? "true" : "false");
  }
  if (el.sidebarBackdrop) {
    const showBackdrop = open && sidebarIsMobile();
    el.sidebarBackdrop.hidden = !showBackdrop;
    el.sidebarBackdrop.setAttribute("aria-hidden", showBackdrop ? "false" : "true");
  }
  if (!sidebarIsMobile()) {
    try {
      localStorage.setItem(SIDEBAR_OPEN_KEY, open ? "1" : "0");
    } catch {
      /* ignore */
    }
  }
  window.requestAnimationFrame(() => {
    map.invalidateSize();
  });
}

function readSidebarOpenPreference() {
  try {
    return localStorage.getItem(SIDEBAR_OPEN_KEY) !== "0";
  } catch {
    return true;
  }
}

function initSidebar() {
  el.sidebarToggle?.addEventListener("click", () => setSidebarOpen(true));
  el.sidebarClose?.addEventListener("click", () => setSidebarOpen(false));
  el.sidebarBackdrop?.addEventListener("click", () => setSidebarOpen(false));

  MOBILE_SIDEBAR_MQ.addEventListener("change", () => {
    if (sidebarIsMobile()) {
      setSidebarOpen(false);
    } else {
      setSidebarOpen(readSidebarOpenPreference());
    }
  });

  if (sidebarIsMobile()) {
    setSidebarOpen(false);
  } else {
    setSidebarOpen(readSidebarOpenPreference());
  }
}

initSidebar();
main();
