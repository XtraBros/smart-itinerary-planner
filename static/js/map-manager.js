const DEFAULT_CENTER = [103.8198, 1.3521];
const DEFAULT_STYLE = "mapbox://styles/mapbox/streets-v12";
const DRAW_JS = "https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-draw/v1.5.0/mapbox-gl-draw.js";
const DRAW_CSS = "https://api.mapbox.com/mapbox-gl-js/plugins/mapbox-gl-draw/v1.5.0/mapbox-gl-draw.css";

let previewMap = null;
let previewMarker = null;
let drawControl = null;
let currentSpotlightPolygon = null;
let mapManagedExternally = false;
let drawAssetsPromise = null;
let uiBound = false;
let hasBootstrappedConfig = false;
let drawButtonRef = null;

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

  drawButtonRef = document.getElementById("startDrawBtn");
  if (drawButtonRef) {
    drawButtonRef.addEventListener("click", startSpotlightDraw);
  }
}

function toggleDrawButton(active) {
  if (!drawButtonRef) return;
  if (active) {
    drawButtonRef.classList.add("active");
  } else {
    drawButtonRef.classList.remove("active");
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
    summaryEl.textContent = "Draw a polygon with the ⬠ control to highlight an area.";
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

  drawControl.deleteAll();
  if (initialPolygon) {
    drawControl.add({
      type: "Feature",
      properties: {},
      geometry: JSON.parse(JSON.stringify(initialPolygon)),
    });
  }
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
  currentSpotlightPolygon = getActivePolygonFromDraw();
  updatePolygonSummary(currentSpotlightPolygon);
  toggleDrawButton(false);
  setStatus(
    document.getElementById("polygonStatus"),
    currentSpotlightPolygon
      ? "Polygon updated. Click “Save Spotlight” to persist."
      : "Polygon removed.",
    currentSpotlightPolygon ? "" : "error"
  );
}

function handleDrawDelete() {
  currentSpotlightPolygon = null;
  updatePolygonSummary(null);
  toggleDrawButton(false);
  setStatus(
    document.getElementById("polygonStatus"),
    "Polygon cleared. Click “Save Spotlight” to persist removal.",
    ""
  );
}

function startSpotlightDraw() {
  const statusEl = document.getElementById("polygonStatus");
  if (!previewMap) {
    setStatus(statusEl, "⚠️ Map preview is still initialising.", "error");
    return;
  }

  const beginDrawMode = () => {
    if (!drawControl) {
      setStatus(statusEl, "⚠️ Drawing controls are still loading.", "error");
      return;
    }
    try {
      toggleDrawButton(true);
      drawControl.changeMode("draw_polygon");
      setStatus(
        statusEl,
        "✏️ Click around the map to define the spotlight polygon, double-click to finish.",
        ""
      );
    } catch (err) {
      console.error("Failed to trigger draw mode:", err);
      setStatus(statusEl, "❌ Unable to start drawing just yet.", "error");
    }
  };

  if (drawControl) {
    beginDrawMode();
    return;
  }

  setStatus(statusEl, "⏳ Preparing drawing controls...", "");
  setupDrawControl(currentSpotlightPolygon)
    .then(beginDrawMode)
    .catch((err) => {
      console.error("Failed to prepare draw control:", err);
      setStatus(statusEl, "❌ Unable to start drawing.", "error");
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

function saveSpotlightPolygon() {
  if (!currentSpotlightPolygon) {
    setStatus(
      document.getElementById("polygonStatus"),
      "❌ Draw a polygon before saving.",
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
      }
    })
    .catch(() => {});
}

function clearSpotlightPolygon() {
  if (drawControl) {
    drawControl.deleteAll();
  }
  currentSpotlightPolygon = null;
  updatePolygonSummary(null);
  toggleDrawButton(false);

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
  toggleDrawButton(false);

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
    });
    return;
  }

  ensureMapReady(previewMap).then(() => {
    setPreviewMarker(centre);
    setupDrawControl(currentSpotlightPolygon);
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
window.startSpotlightDraw = startSpotlightDraw;
