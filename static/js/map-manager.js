const DEFAULT_CENTER = [103.8198, 1.3521];
const DEFAULT_STYLE = "mapbox://styles/mapbox/streets-v12";
const DRAW_JS = "https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-draw/v1.5.0/mapbox-gl-draw.js";
const DRAW_CSS = "https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-draw/v1.5.0/mapbox-gl-draw.css";
const TURF_JS = "https://unpkg.com/@turf/turf@6.5.0/turf.min.js";
const SPOTLIGHT_SOURCE_ID = "spotlight-preview";
const SPOTLIGHT_FILL_LAYER_ID = "spotlight-preview-fill";
const SPOTLIGHT_LINE_LAYER_ID = "spotlight-preview-line";
const TRACE_SOURCE_ID = "spotlight-trace-line";
const TRACE_LAYER_ID = "spotlight-trace-line-layer";
const TRACE_DISTANCE_THRESHOLD_PX = 3;

let previewMap = null;
let previewMarker = null;
let drawControl = null;
let currentSpotlightPolygon = null;
let mapManagedExternally = false;
let drawAssetsPromise = null;
let turfAssetsPromise = null;
let uiBound = false;
let hasBootstrappedConfig = false;
let latestSmoothRequestId = 0;
let pendingSmoothPromise = null;
let isRehydratingDraw = false;
let drawLayerStyleListenerAttached = false;
let tracePrimed = false;
let traceMoveHandler = null;
let traceCoords = [];

const drawEventHandlers = {
  create: () => handleDrawChange(),
  update: () => handleDrawChange(),
  delete: () => handleDrawDelete(),
};

function fetchMapboxToken() {
  return fetch("/config")
    .then((res) => res.json())
    .then((data) => {
      if (data.config && data.config.MAPBOX_ACCESS_TOKEN) {
        mapboxgl.accessToken = data.config.MAPBOX_ACCESS_TOKEN;
      } else {
        console.warn("Mapbox Access Token not found in config.");
      }
    })
    .catch((err) => {
      console.error("Failed to fetch Mapbox token:", err);
    });
}

fetchMapboxToken();

function ensureDrawAssets() {
  if (!document.getElementById("mapbox-draw-css")) {
    const cssLink = document.createElement("link");
    cssLink.id = "mapbox-draw-css";
    cssLink.rel = "stylesheet";
    cssLink.href = DRAW_CSS;
    document.head.appendChild(cssLink);
  }

  if (window.MapboxDraw) {
    return Promise.resolve();
  }

  if (!drawAssetsPromise) {
    drawAssetsPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = DRAW_JS;
      script.onload = resolve;
      script.onerror = reject;
      document.body.appendChild(script);
    });
  }

  return drawAssetsPromise;
}

function ensureTurfAssets() {
  if (window.turf) {
    return Promise.resolve(window.turf);
  }

  if (!turfAssetsPromise) {
    turfAssetsPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = TURF_JS;
      script.onload = () => resolve(window.turf);
      script.onerror = reject;
      document.body.appendChild(script);
    });
  }

  return turfAssetsPromise;
}

function bindUIEvents() {
  if (uiBound) return;
  uiBound = true;

  const updateBtn = document.getElementById("updateMapSettingsBtn");
  if (updateBtn) {
    updateBtn.addEventListener("click", submitMapSettings);
  }

  const saveBtn = document.getElementById("saveSpotlightBtn");
  if (saveBtn) {
    saveBtn.addEventListener("click", saveSpotlightPolygon);
  }

  const clearBtn = document.getElementById("clearSpotlightBtn");
  if (clearBtn) {
    clearBtn.addEventListener("click", clearSpotlightPolygon);
  }
}

function setStatus(element, message, state) {
  if (!element) return;
  element.textContent = message;
  element.className = `status-message ${state || ""}`.trim();
}

function parseCentre(rawCentre) {
  if (!rawCentre) return null;

  if (Array.isArray(rawCentre) && rawCentre.length === 2) {
    return rawCentre.map((val) => Number(val));
  }

  try {
    const parsed =
      typeof rawCentre === "string" ? JSON.parse(rawCentre) : rawCentre;
    if (
      Array.isArray(parsed) &&
      parsed.length === 2 &&
      parsed.every((val) => typeof val === "number")
    ) {
      return parsed;
    }
  } catch (err) {
    console.error("Failed to parse map centre:", err);
  }
  return null;
}

function parsePolygon(rawPolygon) {
  if (!rawPolygon) return null;
  try {
    const parsed =
      typeof rawPolygon === "string" ? JSON.parse(rawPolygon) : rawPolygon;
    if (
      parsed &&
      parsed.type === "Polygon" &&
      Array.isArray(parsed.coordinates)
    ) {
      return parsed;
    }
  } catch (err) {
    console.error("Failed to parse MAP_SPOTLIGHT_POLYGON:", err);
  }
  return null;
}

function populateFormFields(styleURL, center) {
  const styleInput = document.getElementById("mapStyleInput");
  const centerInput = document.getElementById("mapCenterInput");

  if (styleInput && styleURL) {
    styleInput.placeholder = styleURL;
    styleInput.value = styleURL;
  }

  if (centerInput && center) {
    const centreText = center.join(", ");
    centerInput.placeholder = centreText;
    centerInput.value = centreText;
  }
}

function updatePolygonSummary(polygon) {
  const summaryEl = document.getElementById("polygonSummary");
  if (!summaryEl) return;

  if (!polygon) {
    summaryEl.textContent = "Use Trace Outline to highlight an area.";
    return;
  }

  const ring = Array.isArray(polygon.coordinates)
    ? polygon.coordinates[0] || []
    : [];
  const vertCount = ring.length;
  summaryEl.textContent = `Vertices: ${vertCount} • Double-click to finish drawing.`;
}

function setPreviewMarker(center) {
  if (!previewMap || !Array.isArray(center) || center.length !== 2) return;
  const [lng, lat] = center;
  if (typeof lng !== "number" || typeof lat !== "number") return;

  if (!previewMarker) {
    previewMarker = new mapboxgl.Marker().setLngLat([lng, lat]).addTo(previewMap);
  } else {
    previewMarker.setLngLat([lng, lat]);
  }
  previewMap.setCenter([lng, lat]);
}

function ensureMapReady(mapInstance) {
  if (!mapInstance) return Promise.resolve();
  if (mapInstance.loaded()) return Promise.resolve();
  return new Promise((resolve) => mapInstance.once("load", resolve));
}

async function setupDrawControl(initialPolygon) {
  if (!previewMap) return;
  await ensureMapReady(previewMap);
  await ensureDrawAssets();

  if (drawControl) {
    previewMap.off("draw.create", drawEventHandlers.create);
    previewMap.off("draw.update", drawEventHandlers.update);
    previewMap.off("draw.delete", drawEventHandlers.delete);
    try {
      previewMap.removeControl(drawControl);
    } catch (err) {
      console.warn("Failed to remove existing draw control:", err);
    }
  }

  drawControl = new MapboxDraw({
    displayControlsDefault: false,
    controls: {
      polygon: true,
      trash: true,
    },
  });

  previewMap.addControl(drawControl, "top-left");
  previewMap.on("draw.create", drawEventHandlers.create);
  previewMap.on("draw.update", drawEventHandlers.update);
  previewMap.on("draw.delete", drawEventHandlers.delete);
  if (!drawLayerStyleListenerAttached) {
    previewMap.on("styledata", applyDrawLayerStyles);
    drawLayerStyleListenerAttached = true;
  }
  applyDrawLayerStyles();

  refreshDrawGeometry(initialPolygon);
}

function getActivePolygonFromDraw() {
  if (!drawControl) return null;
  const collection = drawControl.getAll();
  const polygons = collection.features.filter(
    (feature) => feature.geometry && feature.geometry.type === "Polygon"
  );
  if (!polygons.length) {
    return null;
  }

  // Keep the most recent polygon and remove older ones to enforce a single spotlight.
  polygons.slice(0, -1).forEach((feature) => drawControl.delete(feature.id));
  const latest = polygons[polygons.length - 1];
  return latest.geometry
    ? JSON.parse(JSON.stringify(latest.geometry))
    : null;
}

function handleDrawChange() {
  if (isRehydratingDraw) {
    return;
  }
  const polygon = getActivePolygonFromDraw();
  if (!polygon) {
    latestSmoothRequestId += 1;
    pendingSmoothPromise = null;
    currentSpotlightPolygon = null;
    setStatus(
      document.getElementById("polygonStatus"),
      "Polygon removed.",
      "error"
    );
    updatePolygonSummary(null);
    renderSpotlightOverlay(null);
    return;
  }

  setStatus(
    document.getElementById("polygonStatus"),
    "✨ Smoothing polygon...",
    ""
  );
  const smoothRequestId = ++latestSmoothRequestId;
  const smoothPromise = smoothPolygonShape(polygon)
    .then((smoothed) => {
      if (smoothRequestId !== latestSmoothRequestId) {
        return;
      }
      currentSpotlightPolygon = smoothed || polygon;
      refreshDrawGeometry(currentSpotlightPolygon);
      updatePolygonSummary(currentSpotlightPolygon);
      renderSpotlightOverlay(currentSpotlightPolygon);
      setStatus(
        document.getElementById("polygonStatus"),
        "Polygon refined. Save to persist.",
        "success"
      );
    })
    .catch((err) => {
      console.error("Failed to smooth polygon:", err);
      currentSpotlightPolygon = polygon;
      refreshDrawGeometry(currentSpotlightPolygon);
      updatePolygonSummary(currentSpotlightPolygon);
      renderSpotlightOverlay(currentSpotlightPolygon);
      setStatus(
        document.getElementById("polygonStatus"),
        "⚠️ Using original polygon (smoother unavailable).",
        "error"
      );
    })
    .finally(() => {
      if (pendingSmoothPromise === smoothPromise) {
        pendingSmoothPromise = null;
      }
    });
  pendingSmoothPromise = smoothPromise;
}

function handleDrawDelete() {
  if (isRehydratingDraw) {
    return;
  }
  currentSpotlightPolygon = null;
  updatePolygonSummary(null);
  renderSpotlightOverlay(null);
  setStatus(
    document.getElementById("polygonStatus"),
    "Polygon cleared. Click “Save Spotlight” to persist removal.",
    ""
  );
}

function startTraceMode() {
  const statusEl = document.getElementById("polygonStatus");
  if (!previewMap) {
    setStatus(statusEl, "⚠️ Map preview is still initialising.", "error");
    return;
  }
  if (traceMoveHandler) {
    setStatus(statusEl, "🖱️ Finish the current trace (release mouse) before starting a new one.", "error");
    return;
  }
  if (tracePrimed) {
    setStatus(statusEl, "Trace mode armed — click and hold on the map to continue tracing.", "");
    return;
  }
  if (!drawControl) {
    setStatus(statusEl, "⏳ Preparing drawing controls...", "");
    setupDrawControl(currentSpotlightPolygon)
      .then(() => startTraceMode())
      .catch((err) => {
        console.error("Failed to prepare trace controls:", err);
        setStatus(statusEl, "❌ Unable to initialise trace mode.", "error");
      });
    return;
  }

  tracePrimed = true;
  setStatus(
    statusEl,
    "Trace mode armed. Click and hold the mouse to start tracing the island outline.",
    ""
  );

  const beginHandler = (event) => {
    previewMap.off("mousedown", beginHandler);
    tracePrimed = false;
    beginTraceSession(event, statusEl);
  };

  previewMap.once("mousedown", beginHandler);
}

function beginTraceSession(event, statusEl) {
  if (!previewMap) return;
  traceCoords = [];
  previewMap.dragPan.disable();
  previewMap.getCanvas().style.cursor = "crosshair";
  addTraceCoordinate(event.lngLat, true);
  renderTraceLine(traceCoords);

  traceMoveHandler = (moveEvent) => {
    addTraceCoordinate(moveEvent.lngLat, false);
  };

  const finishTrace = (evt) => {
    previewMap.off("mousemove", traceMoveHandler);
    previewMap.off("mouseup", finishTrace);
    traceMoveHandler = null;
    previewMap.dragPan.enable();
    previewMap.getCanvas().style.cursor = "";
    renderTraceLine(null);
    if (evt && evt.lngLat) {
      addTraceCoordinate(evt.lngLat, true);
    }
    finalizeTracePolygon(statusEl);
  };

  previewMap.on("mousemove", traceMoveHandler);
  previewMap.once("mouseup", finishTrace);
}

function addTraceCoordinate(lngLat, force) {
  if (!lngLat) return;
  const coord = [lngLat.lng, lngLat.lat];
  if (!traceCoords.length) {
    traceCoords.push(coord);
    renderTraceLine(traceCoords);
    return;
  }

  if (!force) {
    const last = traceCoords[traceCoords.length - 1];
    const lastPoint = previewMap.project({ lng: last[0], lat: last[1] });
    const currentPoint = previewMap.project(lngLat);
    const distance = Math.hypot(
      currentPoint.x - lastPoint.x,
      currentPoint.y - lastPoint.y
    );
    if (distance < TRACE_DISTANCE_THRESHOLD_PX) {
      return;
    }
  }
  traceCoords.push(coord);
  renderTraceLine(traceCoords);
}

function finalizeTracePolygon(statusEl) {
  if (traceCoords.length < 3) {
    traceCoords = [];
    setStatus(statusEl, "❌ Trace needs at least three points.", "error");
    return;
  }
  const closedRing = ensureClosedRing(traceCoords.slice());
  traceCoords = [];
  const polygon = {
    type: "Polygon",
    coordinates: [closedRing],
  };
  currentSpotlightPolygon = polygon;
  refreshDrawGeometry(currentSpotlightPolygon);
  updatePolygonSummary(currentSpotlightPolygon);
  renderSpotlightOverlay(currentSpotlightPolygon);
  setStatus(statusEl, "✅ Trace captured. Adjust or save when ready.", "success");
}

function renderTraceLine(coords) {
  if (!previewMap || !previewMap.getStyle()) return;
  const data = coords && coords.length
    ? {
        type: "Feature",
        properties: {},
        geometry: { type: "LineString", coordinates: coords },
      }
    : { type: "FeatureCollection", features: [] };

  if (previewMap.getSource(TRACE_SOURCE_ID)) {
    previewMap.getSource(TRACE_SOURCE_ID).setData(data);
    return;
  }

  previewMap.addSource(TRACE_SOURCE_ID, { type: "geojson", data });
  previewMap.addLayer({
    id: TRACE_LAYER_ID,
    type: "line",
    source: TRACE_SOURCE_ID,
    paint: {
      "line-color": "#0ea5e9",
      "line-width": 2,
      "line-dasharray": [0.5, 0.75],
    },
  });
}

function buildSettingsPayload() {
  const payload = {};
  const styleInput = document.getElementById("mapStyleInput");
  const centerInput = document.getElementById("mapCenterInput");

  if (styleInput && styleInput.value.trim()) {
    payload.mapbox_style_url = styleInput.value.trim();
  }

  if (centerInput && centerInput.value.trim()) {
    const centreArray = centerInput.value.split(",").map((val) => Number(val.trim()));
    if (
      centreArray.length === 2 &&
      centreArray.every((val) => Number.isFinite(val))
    ) {
      payload.map_centre = centreArray;
    } else {
      setStatus(
        document.getElementById("mapStyleStatus"),
        "❌ Invalid map centre format. Use 'lng, lat'.",
        "error"
      );
      return null;
    }
  }
  return payload;
}

function sendSettingsUpdate(payload, statusElement, successMessage) {
  if (!statusElement) return Promise.resolve();
  setStatus(statusElement, "⏳ Saving...", "");

  return fetch("/admin/update_map_style", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then((res) => res.json().then((body) => ({ status: res.status, body })))
    .then(({ status, body }) => {
      if (status >= 400 || body.error) {
        throw new Error(body.error || "Failed to update settings.");
      }
      setStatus(statusElement, successMessage || "✅ Settings updated.", "success");
      return body;
    })
    .catch((err) => {
      console.error("Failed to update map settings:", err);
      setStatus(statusElement, `❌ ${err.message}`, "error");
      throw err;
    });
}

function submitMapSettings() {
  const payload = buildSettingsPayload();
  if (!payload || Object.keys(payload).length === 0) {
    setStatus(
      document.getElementById("mapStyleStatus"),
      "❌ Provide a style URL and/or centre before saving.",
      "error"
    );
    return;
  }

  sendSettingsUpdate(payload, document.getElementById("mapStyleStatus"))
    .then((data) => {
      if (data.style_url) {
        const styleInput = document.getElementById("mapStyleInput");
        styleInput.value = data.style_url;
        styleInput.placeholder = data.style_url;
      }
      if (Array.isArray(data.map_centre)) {
        const centerInput = document.getElementById("mapCenterInput");
        const centreText = data.map_centre.join(", ");
        centerInput.value = centreText;
        centerInput.placeholder = centreText;
      }
      updateMapPreview(data.style_url, data.map_centre);
    })
    .catch(() => {});
}

async function ensureSmoothingComplete() {
  if (!pendingSmoothPromise) {
    return currentSpotlightPolygon;
  }
  try {
    await pendingSmoothPromise;
  } catch (err) {
    console.warn("Pending smoothing failed:", err);
  }
  return currentSpotlightPolygon;
}

async function saveSpotlightPolygon() {
  await ensureSmoothingComplete();
  if (!currentSpotlightPolygon) {
    setStatus(
      document.getElementById("polygonStatus"),
      "❌ Highlight an area before saving.",
      "error"
    );
    return;
  }

  sendSettingsUpdate(
    { spotlight_polygon: currentSpotlightPolygon },
    document.getElementById("polygonStatus"),
    "✅ Spotlight polygon saved."
  )
    .then((data) => {
      if (data.spotlight_polygon) {
        currentSpotlightPolygon = data.spotlight_polygon;
        updatePolygonSummary(currentSpotlightPolygon);
        refreshDrawGeometry(currentSpotlightPolygon);
      }
    })
    .catch(() => {});
}

async function clearSpotlightPolygon() {
  await ensureSmoothingComplete();
  if (drawControl) {
    drawControl.deleteAll();
  }
  currentSpotlightPolygon = null;
  updatePolygonSummary(null);
  renderSpotlightOverlay(null);

  sendSettingsUpdate(
    { spotlight_polygon: null },
    document.getElementById("polygonStatus"),
    "✅ Spotlight polygon cleared."
  ).catch(() => {});
}

function updateMapPreview(styleURL, center, polygonOverride) {
  if (!previewMap) return;
  const targetPolygon =
    typeof polygonOverride === "undefined" ? currentSpotlightPolygon : polygonOverride;

  const applyUpdates = () => {
    if (center && center.length === 2) {
      setPreviewMarker(center);
    }
    setupDrawControl(targetPolygon);
    applyDrawLayerStyles();
    renderSpotlightOverlay(targetPolygon);
  };

  if (styleURL) {
    previewMap.setStyle(styleURL);
    previewMap.once("styledata", () => {
      ensureMapReady(previewMap).then(applyUpdates);
    });
  } else {
    ensureMapReady(previewMap).then(applyUpdates);
  }
}

function bootstrapMapManager(config) {
  hasBootstrappedConfig = true;
  bindUIEvents();
  const cfg = config || {};
  const styleURL = cfg.MAPBOX_STYLE_URL || DEFAULT_STYLE;
  const centre = parseCentre(cfg.MAP_CENTRE) || DEFAULT_CENTER;
  currentSpotlightPolygon = parsePolygon(cfg.MAP_SPOTLIGHT_POLYGON);

  populateFormFields(styleURL, centre);
  updatePolygonSummary(currentSpotlightPolygon);

  if (!previewMap) {
    previewMap = new mapboxgl.Map({
      container: "mapPreview",
      style: styleURL,
      center: centre,
      zoom: 12,
    });

    previewMap.on("load", () => {
      setPreviewMarker(centre);
      previewMap.resize();
      setupDrawControl(currentSpotlightPolygon);
      renderSpotlightOverlay(currentSpotlightPolygon);
    });
    return;
  }

  ensureMapReady(previewMap).then(() => {
    setPreviewMarker(centre);
    setupDrawControl(currentSpotlightPolygon);
    renderSpotlightOverlay(currentSpotlightPolygon);
  });
}

function refreshDrawGeometry(polygon) {
  if (!drawControl) return;
  isRehydratingDraw = true;
  drawControl.deleteAll();
  if (polygon) {
    drawControl.add({
      type: "Feature",
      properties: {},
      geometry: JSON.parse(JSON.stringify(polygon)),
    });
  }
  setTimeout(() => {
    isRehydratingDraw = false;
  }, 0);
}

async function smoothPolygonShape(polygon) {
  if (!polygon) return null;
  await ensureTurfAssets();
  const baseRing = (polygon.coordinates && polygon.coordinates[0]) || [];
  const candidateRing = dedupeRing(baseRing);
  if (candidateRing.length < 4) {
    return {
      type: "Polygon",
      coordinates: [ensureClosedRing(candidateRing)],
    };
  }

  const fc = window.turf.featureCollection(
    candidateRing.map((coord) => window.turf.point(coord))
  );
  const maxEdge = estimateHullEdgeLength(candidateRing);

  let hull = window.turf.concave(fc, { maxEdge });
  if (!hull && candidateRing.length >= 3) {
    hull = window.turf.convex(fc);
  }
  if (!hull || !hull.geometry || hull.geometry.type !== "Polygon") {
    return {
      type: "Polygon",
      coordinates: [ensureClosedRing(candidateRing)],
    };
  }

  const smoothedCoordinates = (hull.geometry.coordinates || []).map((ring) =>
    ensureClosedRing(ring)
  );

  return {
    type: "Polygon",
    coordinates: smoothedCoordinates.length
      ? smoothedCoordinates
      : [ensureClosedRing(candidateRing)],
  };
}

function dedupeRing(ring) {
  if (!Array.isArray(ring)) return [];
  const cleaned = [];
  ring.forEach((coord) => {
    if (
      !Array.isArray(coord) ||
      coord.length !== 2 ||
      Number.isNaN(coord[0]) ||
      Number.isNaN(coord[1])
    ) {
      return;
    }
    const last = cleaned[cleaned.length - 1];
    if (!last || last[0] !== coord[0] || last[1] !== coord[1]) {
      cleaned.push([Number(coord[0]), Number(coord[1])]);
    }
  });
  if (cleaned.length && cleaned[0][0] === cleaned[cleaned.length - 1][0] && cleaned[0][1] === cleaned[cleaned.length - 1][1]) {
    cleaned.pop();
  }
  return cleaned;
}

function ensureClosedRing(ring) {
  if (!Array.isArray(ring) || !ring.length) {
    return ring || [];
  }
  const first = ring[0];
  const last = ring[ring.length - 1];
  if (!last || first[0] !== last[0] || first[1] !== last[1]) {
    return [...ring, [first[0], first[1]]];
  }
  return ring;
}

function estimateHullEdgeLength(coords) {
  if (!window.turf || coords.length < 2) {
    return 0.5;
  }
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;
  coords.forEach(([lng, lat]) => {
    if (lng < minLng) minLng = lng;
    if (lng > maxLng) maxLng = lng;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  });
  const lower = window.turf.point([minLng, minLat]);
  const upper = window.turf.point([maxLng, maxLat]);
  const diagonal = window.turf.distance(lower, upper, { units: "kilometers" }) || 0.5;
  return Math.max(diagonal * 0.4, 0.1);
}

function applyDrawLayerStyles() {
  if (!previewMap || !previewMap.getStyle()) return;
  const fillInactive = "#fb923c";
  const fillActive = "#fde047";
  const borderColor = "#ea580c";
  const layers = [
    { id: "gl-draw-polygon-fill-inactive", props: { "fill-color": fillInactive, "fill-opacity": 0.4 } },
    { id: "gl-draw-polygon-fill-active", props: { "fill-color": fillActive, "fill-opacity": 0.6 } },
    { id: "gl-draw-polygon-stroke-inactive", props: { "line-color": borderColor, "line-width": 2 } },
    { id: "gl-draw-polygon-stroke-active", props: { "line-color": borderColor, "line-width": 3 } },
  ];
  layers.forEach(({ id, props }) => {
    if (previewMap.getLayer(id)) {
      Object.entries(props).forEach(([prop, value]) => {
        try {
          previewMap.setPaintProperty(id, prop, value);
        } catch (err) {
          console.warn(`Failed to style ${id}`, err);
        }
      });
    }
  });
}

function renderSpotlightOverlay(polygon) {
  if (!previewMap || !previewMap.getStyle()) return;
  const data = polygon
    ? {
        type: "Feature",
        properties: {},
        geometry: JSON.parse(JSON.stringify(polygon)),
      }
    : { type: "FeatureCollection", features: [] };

  if (previewMap.getSource(SPOTLIGHT_SOURCE_ID)) {
    previewMap.getSource(SPOTLIGHT_SOURCE_ID).setData(data);
    return;
  }

  previewMap.addSource(SPOTLIGHT_SOURCE_ID, {
    type: "geojson",
    data,
  });
  previewMap.addLayer({
    id: SPOTLIGHT_FILL_LAYER_ID,
    type: "fill",
    source: SPOTLIGHT_SOURCE_ID,
    paint: {
      "fill-color": "#22d3ee",
      "fill-opacity": 0.25,
    },
  });
  previewMap.addLayer({
    id: SPOTLIGHT_LINE_LAYER_ID,
    type: "line",
    source: SPOTLIGHT_SOURCE_ID,
    paint: {
      "line-color": "#0e7490",
      "line-width": 3,
      "line-dasharray": [1, 1],
    },
  });
}


function fetchMapConfig() {
  if (hasBootstrappedConfig) return;

  fetch("/config")
    .then((res) => res.json())
    .then((data) => {
      bootstrapMapManager(data.config || {});
    })
    .catch((err) => {
      console.error("Failed to fetch config:", err);
      setStatus(
        document.getElementById("mapStyleStatus"),
        "⚠️ Unable to fetch config",
        "error"
      );
    });
}

document.addEventListener("DOMContentLoaded", () => {
  bindUIEvents();
  fetchMapConfig();
});

window.attachMapManagerUI = function attachMapManagerUI(mapInstance, cfg) {
  previewMap = mapInstance || previewMap;
  mapManagedExternally = Boolean(mapInstance);
  bootstrapMapManager(cfg);
};

window.submitMapSettings = submitMapSettings;
window.saveSpotlightPolygon = saveSpotlightPolygon;
window.clearSpotlightPolygon = clearSpotlightPolygon;
window.startTraceMode = startTraceMode;
