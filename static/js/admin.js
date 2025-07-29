// static/js/admin.js
const config = {
    content: [{
        type: 'row',
        content: []
    }]
};

const layout = new GoldenLayout(config, document.getElementById('main-area'));

layout.registerComponent('html-component', function(container, state) {
    fetch(`/admin/screen/${state.name}`)
        .then(res => res.text())
        .then(html => {
            container.getElement().html(`
                <div class="tab-content-scroll">${html}</div>
            `);
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
