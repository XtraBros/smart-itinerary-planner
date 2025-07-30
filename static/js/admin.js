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
const layout = new GoldenLayout(config, document.getElementById('main-area'));

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
            el.style.height = "100%";

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
                    const script = document.createElement('script');
                    script.src = '/static/js/map-manager.js';
                    script.onload = () => {
                        console.log('map-manager.js loaded');
                        if (typeof fetchMapConfig === 'function') fetchMapConfig();
                    };
                    script.onerror = () => console.error('Failed to load map-manager.js');
                    document.head.appendChild(script);
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

layout.init();
function openComponent(name, title) {
    // If no root content, create a root row container
    if (!layout.root.contentItems.length) {
        layout.root.addChild({
            type: 'row',
            content: []
        });
    }

    const rootRow = layout.root.contentItems[0];

    // Search for an existing tab with the same componentState.name
    for (const item of rootRow.contentItems) {
        // Defensive check if item is component and has the right state
        if (
            item.type === 'component' &&
            item.config.componentState &&
            item.config.componentState.name === name
        ) {
            // Activate the found tab and bring it to front
            rootRow.setActiveContentItem(item);
            return;  // Stop here, no new tab created
        }
    }

    // No existing tab found, add new one
    rootRow.addChild({
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