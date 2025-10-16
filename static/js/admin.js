// static/js/admin.js
const config = {
    content: [{
        type: 'row',
        content: []
    }]
};
let mapboxAccessToken = null;

function fetchMapboxToken() {
  return fetch('/config')
    .then(res => res.json())
    .then(data => {
      if (data.config && data.config.MAPBOX_ACCESS_TOKEN) {
        mapboxAccessToken = data.config.MAPBOX_ACCESS_TOKEN;
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
const layout = new GoldenLayout(config, $('#main-area'));
layout.init();
layout.updateSize($('#main-area').width(), $('#main-area').height());
layout.registerComponent('html-component', function(container, state) {
    function loadScript(src) {
        return new Promise((resolve, reject) => {
            const s = document.createElement('script');
            s.src = src;
            s.onload = resolve;
            s.onerror = reject;
            document.head.appendChild(s);
        });
    }

    fetch(`/admin/screen/${state.name}`)
        .then(res => res.text())
        .then(html => {
            const htmlWithoutScripts = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gm, '');
            const el = container.getElement()[0];
            el.innerHTML = htmlWithoutScripts;
            el.style.overflowY = "auto";
            el.style.width = '100%';
            el.style.height = '100%';
            el.style.minWidth = '0';
            el.style.minHeight = '0';
            switch (state.name) {
                case 'rag-manager': {
                    const script = document.createElement('script');
                    script.src = '/static/js/rag-manager.js';
                    script.onload = () => {
                        console.log('rag-manager.js loaded');
                        if (typeof fetchUnits === 'function') fetchUnits();
                    };
                    script.onerror = () => console.error('Failed to load rag-manager.js');
                    document.head.appendChild(script);
                    break;
                }

                case 'llm-manager': {
                    const script = document.createElement('script');
                    script.src = '/static/js/llm-manager.js';
                    script.onload = () => console.log('llm-manager.js loaded');
                    script.onerror = () => console.error('Failed to load llm-manager.js');
                    document.head.appendChild(script);
                    break;
                }

                case 'map-manager': {
                    console.log('Loading Map Manager...');
                  
                    // Load Mapbox CSS + JS once
                    if (!document.querySelector("link[href*='mapbox-gl.css']")) {
                      const css = document.createElement('link');
                      css.rel = 'stylesheet';
                      css.href = 'https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.css';
                      document.head.appendChild(css);
                    }
                  
                    function loadMapbox() {
                      return new Promise((resolve, reject) => {
                        if (window.mapboxgl) return resolve();
                        const script = document.createElement('script');
                        script.src = 'https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.js';
                        script.onload = resolve;
                        script.onerror = reject;
                        document.head.appendChild(script);
                      });
                    }
                  
                    // Initialize the map directly in this component
                    async function initMapManager() {
                      try {
                        // 1️⃣ Fetch config (token + style)
                        const res = await fetch('/config');
                        const data = await res.json();
                        const cfg = data.config || {};
                  
                        if (!cfg.MAPBOX_ACCESS_TOKEN) {
                          console.error('Missing MAPBOX_ACCESS_TOKEN in config.');
                          return;
                        }
                  
                        // 2️⃣ Set up Mapbox
                        await loadMapbox();
                        mapboxgl.accessToken = cfg.MAPBOX_ACCESS_TOKEN;
                  
                        const mapContainer = document.getElementById('mapPreview');
                        if (!mapContainer) {
                          console.warn('Map preview container not found in tab content.');
                          return;
                        }
                  
                        const styleURL = cfg.MAPBOX_STYLE_URL || 'mapbox://styles/mapbox/streets-v11';
                        let center = [103.8198, 1.3521];
                        if (cfg.MAP_CENTRE) {
                          try {
                            const parsed = JSON.parse(cfg.MAP_CENTRE);
                            if (Array.isArray(parsed) && parsed.length === 2) center = parsed;
                          } catch (e) {
                            console.warn('Invalid MAP_CENTRE format in config');
                          }
                        }
                  
                        // 3️⃣ Initialize the Mapbox map inside #mapPreview
                        const map = new mapboxgl.Map({
                          container: 'mapPreview',
                          style: styleURL,
                          center: center,
                          zoom: 12
                        });
                  
                        map.on('load', () => {
                          new mapboxgl.Marker().setLngLat(center).addTo(map);
                          map.resize();
                        });
                  
                        // 4️⃣ Optionally load map-manager.js for button logic
                        const script = document.createElement('script');
                        script.src = '/static/js/map-manager.js';
                        script.onload = () => {
                          console.log('map-manager.js loaded — attached to UI controls.');
                          if (typeof window.attachMapManagerUI === 'function') {
                            window.attachMapManagerUI(map, cfg);
                          }
                        };
                        document.head.appendChild(script);
                  
                      } catch (err) {
                        console.error('Failed to initialize Map Manager:', err);
                      }
                    }
                  
                    initMapManager();
                    break;
                  }

                case 'analytics': {
                    console.log('Loading analytics dependencies...');
                    loadScript("https://cdn.jsdelivr.net/npm/chart.js")
                        .then(() => loadScript("https://cdn.plot.ly/plotly-latest.min.js"))
                        .then(() => loadScript("/static/js/analytics.js"))
                        .then(() => {
                            console.log("All analytics scripts loaded.");
                            if (typeof initAnalytics === 'function') initAnalytics();
                        })
                        .catch(err => console.error("Failed to load analytics dependencies:", err));

                    container.on('resize', () => {
                        if (typeof window.replotAnalytics === 'function') {
                            window.replotAnalytics();
                        }
                    });

                    break;
                }

                case 'graph-viewer': {
                    console.log('Loading Mapbox for graph-viewer...');
                
                    // Inject Mapbox CSS if not already present
                    if (!document.querySelector("link[href*='mapbox-gl.css']")) {
                        const mapboxCSS = document.createElement('link');
                        mapboxCSS.rel = 'stylesheet';
                        mapboxCSS.href = 'https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.css';
                        document.head.appendChild(mapboxCSS);
                    }
                
                    loadScript("https://api.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.js")
                        .then(() => fetch('/config'))
                        .then(res => res.json())
                        .then(data => {
                            mapboxgl.accessToken = data.config.MAPBOX_ACCESS_TOKEN;
                
                            // Clear any previous content
                            el.innerHTML = '';
                
                            // Create a unique container div for this instance
                            const mapDiv = document.createElement('div');
                            const mapId = `map-${Date.now()}`; // ensure unique ID
                            mapDiv.id = mapId;
                            mapDiv.style.width = '100%';
                            mapDiv.style.height = '100%';
                            el.appendChild(mapDiv);
                
                            const mapInstance = new mapboxgl.Map({
                                container: mapId,
                                style: 'mapbox://styles/mapbox/streets-v12',
                                center: [103.82, 1.25],
                                zoom: 15
                            });
                
                            mapInstance.on('load', async () => {
                                const response = await fetch('/admin/graph_data');
                                const geojson = await response.json();
                
                                mapInstance.addSource('graph', {
                                    type: 'geojson',
                                    data: geojson
                                });
                
                                mapInstance.addLayer({
                                    id: 'nodes',
                                    type: 'circle',
                                    source: 'graph',
                                    filter: ['==', '$type', 'Point'],
                                    paint: {
                                        'circle-radius': 6,
                                        'circle-color': '#FF5733'
                                    }
                                });
                
                                mapInstance.addLayer({
                                    id: 'edges',
                                    type: 'line',
                                    source: 'graph',
                                    filter: ['==', '$type', 'LineString'],
                                    paint: {
                                        'line-width': [
                                            'interpolate',
                                            ['linear'],
                                            ['get', 'weight'],
                                            0, 1,
                                            100, 6
                                        ],
                                        'line-color': '#00BFFF',
                                        'line-opacity': 0.6
                                    }
                                });
                
                                mapInstance.on('click', 'nodes', (e) => {
                                    const name = e.features[0].properties.name;
                                    new mapboxgl.Popup()
                                        .setLngLat(e.lngLat)
                                        .setHTML(`<strong>${name}</strong>`)
                                        .addTo(mapInstance);
                                });
                
                                mapInstance.on('mouseenter', 'nodes', () => {
                                    mapInstance.getCanvas().style.cursor = 'pointer';
                                });
                                mapInstance.on('mouseleave', 'nodes', () => {
                                    mapInstance.getCanvas().style.cursor = '';
                                });
                            });
                        })
                        .catch(err => {
                            console.error('Failed to initialize Mapbox graph-viewer:', err);
                        });
                
                    break;
                }                

                default:
                    console.warn(`No specific handler for ${state.name}`);
            }
        });
});


function findComponentByName(contentItem, name) {
    if (contentItem.type === 'component' &&
        contentItem.config.componentState &&
        contentItem.config.componentState.name === name) {
        return contentItem;
    }
    if (contentItem.contentItems) {
        for (const child of contentItem.contentItems) {
            const found = findComponentByName(child, name);
            if (found) return found;
        }
    }
    return null;
}

function openComponent(name, title) {
    if (!layout.root.contentItems.length) {
        layout.root.addChild({
            type: 'row',
            content: []
        });
    }

    // Search entire layout tree for component
    const existing = findComponentByName(layout.root, name);
    if (existing) {
        existing.parent.setActiveContentItem(existing);  // activate its stack
        return;
    }

    // No existing tab found → add new one
    layout.root.contentItems[0].addChild({
        type: 'component',
        componentName: 'html-component',
        title: title,
        componentState: { name },
        width: 60
    });
}

// expose openComponent globally so sidebar can call it
window.openComponent = openComponent;

document.addEventListener('DOMContentLoaded', () => {
    const menu = document.getElementById('menu');
    if (menu) {
        menu.querySelectorAll('li').forEach(li => {
            li.addEventListener('click', () => {
                const name = li.dataset.component;
                const title = li.dataset.title;
                openComponent(name, title);
            });
        });
    }
});
function resizeLayout() {
    layout.updateSize($('#main-area').width(), $('#main-area').height());
}

window.addEventListener('resize', resizeLayout);

const toggleBtn = document.getElementById("sidebar-toggle");
const sidebar = document.querySelector(".sidebar");
const mainArea = document.getElementById("main-area");

toggleBtn.addEventListener("click", () => {
    sidebar.classList.toggle("collapsed");
    setTimeout(() => {
        // Resize GoldenLayout to match main-area
        layout.updateSize(mainArea.offsetWidth, mainArea.offsetHeight);
    }, 310); // after sidebar transition
});

document.addEventListener('DOMContentLoaded', () => {
    const overlay = document.getElementById("landing-overlay");

    // Landing page buttons
    document.querySelectorAll('.grid-button').forEach(btn => {
        btn.addEventListener('click', () => {
            const component = btn.dataset.component;
            const title = btn.dataset.title;

            // Hide overlay
            overlay.style.display = "none";

            // Open the component in GoldenLayout
            if (window.openComponent) {
                window.openComponent(component, title);
            }
        });
    });

    // Function to check if any component tabs exist
    function hasOpenComponents() {
        return layout.root.getItemsByType('component').length > 0;
    }

// Show overlay if no components remain

layout.on('itemDestroyed', () => {
    setTimeout(() => {
        // Grab the root GoldenLayout container
        const lmRoot = document.querySelector('.lm_goldenlayout.lm_item.lm_root');
        
        if (lmRoot) {
            console.log("lmRoot children:", lmRoot.children.length); // debug
            if (lmRoot.children.length === 0) {
                overlay.style.display = "flex";
            }
        } else {
            console.warn("lm_root container not found!");
        }
    }, 50);
});
});
