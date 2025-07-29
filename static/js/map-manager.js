window.map = window.map || null;function

fetchMapboxToken() {
    return fetch('/config')
      .then(res => res.json())
      .then(data => {
        if (data.config && data.config.MAPBOX_ACCESS_TOKEN) {
          mapboxgl.accessToken =data.config.MAPBOX_ACCESS_TOKEN;
          console.log("Mapbox Access Token loaded successfully:");
        } else {
          console.warn("Mapbox Access Token not found in config.");
        }
      })
      .catch(err => {
        console.error("Failed to fetch Mapbox token:", err);
      });
}
  
// Call fetchMapboxToken() when admin.js loads or when you initialize the layout
fetchMapboxToken();
function initializeMap(styleURL, center) {
  if (map) {
    map.setStyle(styleURL);
    map.setCenter(center);
    return;
  }

  map = new mapboxgl.Map({
    container: "mapPreview",
    style: styleURL,
    center: center,
    zoom: 12,
  });

  new mapboxgl.Marker().setLngLat(center).addTo(map);
}

function fetchMapConfig() {
  fetch("/config")
    .then((res) => res.json())
    .then((data) => {
      const config = data.config;
      let styleURL = config.MAPBOX_STYLE_URL;
      let center = [103.8198, 1.3521]; // default Singapore center

      if (styleURL) {
        document.getElementById("mapStyleInput").placeholder = styleURL;
      }

      if (config.MAP_CENTRE) {
        try {
          const parsed = JSON.parse(config.MAP_CENTRE);
          if (
            Array.isArray(parsed) &&
            parsed.length === 2 &&
            parsed.every((val) => typeof val === "number")
          ) {
            center = parsed;
            document.getElementById("mapCenterInput").placeholder =
              parsed.join(", ");
          }
        } catch (e) {
          console.error("Error parsing MAP_CENTRE:", e);
        }
      }

      if (styleURL && center) {
        initializeMap(styleURL, center);
      }
    })
    .catch((err) => {
      console.error("Failed to fetch config:", err);
      document.getElementById("mapStyleStatus").textContent =
        "⚠️ Unable to fetch config";
      document.getElementById("mapStyleStatus").className =
        "status-message error";
    });
}

function submitMapSettings() {
  const styleUrl = document.getElementById("mapStyleInput").value.trim();
  const centreInput = document.getElementById("mapCenterInput").value.trim();
  const status = document.getElementById("mapStyleStatus");

  status.textContent = "⏳ Updating...";
  status.className = "status-message";

  const payload = {};
  if (styleUrl) payload.mapbox_style_url = styleUrl;

  if (centreInput) {
    const centreArray = centreInput.split(",").map(Number);
    if (centreArray.length !== 2 || centreArray.some(isNaN)) {
      status.textContent = "❌ Invalid map centre format. Use 'lng,lat'.";
      status.className = "status-message error";
      return;
    }
    payload.map_centre = centreArray;
  }

  if (!payload.mapbox_style_url && !payload.map_centre) {
    status.textContent =
      "❌ Please provide either a style URL or map centre.";
    status.className = "status-message error";
    return;
  }

  fetch("/admin/update_map_style", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
    .then((res) => res.json())
    .then((data) => {
      if (data.error) {
        status.textContent = `❌ ${data.error}`;
        status.className = "status-message error";
      } else {
        status.textContent = `✅ Updated: ${data.message}`;
        status.className = "status-message success";

        // Update map preview immediately
        const updatedStyle =
          data.style_url || document.getElementById("mapStyleInput").placeholder;
        const updatedCentre =
          data.map_centre ||
          document
            .getElementById("mapCenterInput")
            .placeholder.split(",")
            .map(Number);

        initializeMap(updatedStyle, updatedCentre);
      }
    })
    .catch((err) => {
      console.error(err);
      status.textContent = "❌ Failed to update";
      status.className = "status-message error";
    });
}

window.addEventListener("DOMContentLoaded", fetchMapConfig);