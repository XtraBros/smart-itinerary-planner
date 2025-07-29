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
    fetch(`/admin/screen/${state.name}`)
        .then(res => res.text())
        .then(html => {
            // Remove any inline script tags from the HTML (if any)
            const htmlWithoutScripts = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gm, '');

            const el = container.getElement()[0];
            el.innerHTML = htmlWithoutScripts;

            // If this is the rag-manager tab, dynamically load rag-manager.js script
            if (state.name === 'rag-manager') {
                // Create a new script element for rag-manager.js
                const script = document.createElement('script');
                script.src = '/static/js/rag-manager.js';
                script.onload = () => {
                    console.log('rag-manager.js loaded');
                    // Optionally, call fetchUnits() or any init function from rag-manager.js here if needed
                    if (typeof fetchUnits === 'function') {
                        fetchUnits();
                    }
                };
                script.onerror = () => {
                    console.error('Failed to load rag-manager.js');
                };
                document.head.appendChild(script);
            }
            else if (state.name === 'llm-manager') {
                // Create a new script element for rag-manager.js
                const script = document.createElement('script');
                script.src = '/static/js/llm-manager.js';
                script.onload = () => {
                    console.log('llm-manager.js loaded');
                };
                script.onerror = () => {
                    console.error('Failed to load rag-manager.js');
                };
                document.head.appendChild(script);
            }
            else if (state.name === 'map-manager') {
                // Create a new script element for rag-manager.js
                const script = document.createElement('script');
                script.src = '/static/js/map-manager.js';
                script.onload = () => {
                    console.log('map-manager.js loaded');
                    // Optionally, call fetchUnits() or any init function from rag-manager.js here if needed
                    if (typeof fetchMapConfig === 'function') {
                        fetchMapConfig();
                    }
                };
                script.onerror = () => {
                    console.error('Failed to load rag-manager.js');
                };
                document.head.appendChild(script);
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

layout.registerComponent('map-manager', function(container, state) {
    container.getElement().html('<div id="map" style="width:100%; height:100%;"></div>');

    fetch('/config')
        .then(response => response.json())
        .then(data => {
            mapboxgl.accessToken = data.config.MAPBOX_ACCESS_TOKEN;
            console.log("Mapbox token loaded:", mapboxgl.accessToken);
            if (window.map) {
                window.map.remove(); // destroy old map if exists
                window.map = null;
            }

            window.map = new mapboxgl.Map({
                container: 'map',
                style: 'mapbox://styles/mapbox/streets-v12',
                center: [103.82, 1.25],
                zoom: 15
            });

            window.map.on('load', async () => {
                const response = await fetch('/admin/graph_data');
                const geojson = await response.json();

                window.map.addSource('graph', {
                    type: 'geojson',
                    data: geojson
                });

                window.map.addLayer({
                    id: 'nodes',
                    type: 'circle',
                    source: 'graph',
                    filter: ['==', '$type', 'Point'],
                    paint: {
                        'circle-radius': 6,
                        'circle-color': '#FF5733'
                    }
                });

                window.map.addLayer({
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

                window.map.on('click', 'nodes', (e) => {
                    const name = e.features[0].properties.name;
                    new mapboxgl.Popup()
                        .setLngLat(e.lngLat)
                        .setHTML(`<strong>${name}</strong>`)
                        .addTo(window.map);
                });

                window.map.on('mouseenter', 'nodes', () => {
                    window.map.getCanvas().style.cursor = 'pointer';
                });
                window.map.on('mouseleave', 'nodes', () => {
                    window.map.getCanvas().style.cursor = '';
                });
            });
        })
        .catch(err => {
            console.error("Error loading Mapbox token:", err);
        });
});