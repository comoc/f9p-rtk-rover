// app.js - SSE client + Leaflet renderer

const map = L.map("map").setView([35.681236, 139.767125], 17);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
}).addTo(map);

const trailLine = L.polyline([], { color: "#2563eb", weight: 3, opacity: 0.7 }).addTo(map);
const marker = L.circleMarker([0, 0], {
  radius: 7,
  color: "#1f2937",
  weight: 2,
  fillColor: "#10b981",
  fillOpacity: 1,
});

let firstFix = true;

const statusBadge = document.getElementById("status-badge");
const connDot = document.getElementById("conn-dot");
const connLabel = document.getElementById("conn-label");

const elements = {
  lat: document.getElementById("m-lat"),
  lon: document.getElementById("m-lon"),
  alt: document.getElementById("m-alt"),
  sats: document.getElementById("m-sats"),
  hdop: document.getElementById("m-hdop"),
  rtcm: document.getElementById("m-rtcm"),
  rtcmAge: document.getElementById("m-rtcm-age"),
  ts: document.getElementById("m-ts"),
};

const STATUS_CLASS = {
  "NO FIX":         "badge badge-nofix",
  "3D/SINGLE":      "badge badge-single",
  "DGNSS":          "badge badge-dgnss",
  "RTK FLOAT":      "badge badge-float",
  "RTK FIXED":      "badge badge-fixed",
  "DEAD RECKONING": "badge badge-single",
};

const STATUS_FILL = {
  "NO FIX":    "#ef4444",
  "3D/SINGLE": "#f59e0b",
  "DGNSS":     "#3b82f6",
  "RTK FLOAT": "#f97316",
  "RTK FIXED": "#10b981",
};

function fmt(v, digits) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Number(v).toFixed(digits);
}

function setConn(connected) {
  if (connected) {
    connDot.className = "dot-connected";
    connLabel.textContent = "connected";
  } else {
    connDot.className = "dot-disconnected";
    connLabel.textContent = "disconnected";
  }
}

function renderState(state) {
  if (!state) return;

  const status = state.status || "NO DATA";
  statusBadge.textContent = status;
  statusBadge.className = STATUS_CLASS[status] || "badge badge-none";

  elements.lat.textContent = fmt(state.lat, 8);
  elements.lon.textContent = fmt(state.lon, 8);
  elements.alt.textContent = state.alt !== null && state.alt !== undefined ? `${fmt(state.alt, 2)} m` : "—";
  elements.sats.textContent = state.sats ?? "—";
  elements.hdop.textContent = fmt(state.hdop, 2);
  elements.rtcm.textContent = state.rtcm_bytes ?? "—";
  elements.rtcmAge.textContent = state.rtcm_age !== null && state.rtcm_age !== undefined
    ? `${fmt(state.rtcm_age, 1)} s` : "—";

  if (state.ts) {
    elements.ts.textContent = new Date(state.ts * 1000).toLocaleTimeString();
  }

  if (state.lat !== null && state.lat !== undefined &&
      state.lon !== null && state.lon !== undefined) {
    const pos = [state.lat, state.lon];

    marker.setLatLng(pos);
    marker.setStyle({ fillColor: STATUS_FILL[status] || "#9ca3af" });
    if (!map.hasLayer(marker)) marker.addTo(map);

    trailLine.addLatLng(pos);

    if (firstFix) {
      map.setView(pos, 18);
      firstFix = false;
    }
  }
}

function renderTrail(points) {
  if (!points || !points.length) return;
  trailLine.setLatLngs(points);
}

function connect() {
  const es = new EventSource("/api/stream");

  es.onopen = () => setConn(true);

  es.onmessage = (ev) => {
    try {
      const payload = JSON.parse(ev.data);
      if (payload.trail) renderTrail(payload.trail);
      if (payload.state) renderState(payload.state);
    } catch (e) {
      console.error("parse error", e);
    }
  };

  es.onerror = () => {
    setConn(false);
    es.close();
    setTimeout(connect, 2000);
  };
}

connect();
