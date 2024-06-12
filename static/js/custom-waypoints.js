// Event listener for 'Add Waypoint' button
document.getElementById('add-waypoint').addEventListener('click', function() {
    map.getCanvas().style.cursor = 'crosshair'; // Change cursor to crosshair

    // Listen for a click on the map
    map.once('click', function(e) {
        var lngLat = e.lngLat;

        // Show the waypoint form
        var formContainer = document.getElementById('waypoint-form-container');
        formContainer.style.display = 'block';

        // Save button click handler
        document.getElementById('save-waypoint').onclick = function() {
            var title = document.getElementById('waypoint-title').value;
            var notes = document.getElementById('waypoint-notes').value;

            addCustomWaypoint(title, notes, lngLat);
            formContainer.style.display = 'none';
            map.getCanvas().style.cursor = ''; // Reset cursor after adding waypoint
        };

        // Cancel button click handler
        document.getElementById('cancel-waypoint').onclick = function() {
            formContainer.style.display = 'none';
            map.getCanvas().style.cursor = ''; // Reset cursor after canceling
        };
    });
});

//////////////////////////////////////////////////////////////////////////////////////////////////
document.getElementById('generate-route').addEventListener('click', function() {
    generateCustomRoute(waypoints);
});

// Function to add a custom waypoint with title and notes
function addCustomWaypoint(title, notes, lngLat) {
    // Concatenate latitude and longitude with the existing notes
    var coordinates = "Coordinates: " + lngLat.lat.toFixed(6) + ", " + lngLat.lng.toFixed(6);
    var fullNotes = notes + "<br>" + coordinates; // Add coordinates to notes

    // Construct popup content
    var popupContent = "<h3>" + title + "</h3>" + "<p>" + fullNotes + "</p>";

    // Create marker with popup and add it to the map
    new mapboxgl.Marker()
        .setLngLat(lngLat)
        .setPopup(new mapboxgl.Popup().setHTML(popupContent))
        .addTo(map);
    // Add waypoint to the array
    waypoints.push(lngLat);
}
// Function to generate a custom route using Mapbox Directions API
function generateCustomRoute(waypoints) {
    // Clear existing routes
    if (map.getSource('route')) {
        map.removeLayer('route');
        map.removeSource('route');
    }
    if (waypoints.length < 2) {
        alert("At least two waypoints are required to generate a route.");
        return;
    }
    // sort waypoints to update route
    waypoints.sort(function(a, b) {
        return a.lat - b.lat;
    });
    var coordinates = waypoints.map(function(point) {
        return [point.lng, point.lat];
    });

    var directionsRequest = 'https://api.mapbox.com/directions/v5/mapbox/walking/' + coordinates.join(';') + '?geometries=geojson&access_token=' + mapboxgl.accessToken;

    fetch(directionsRequest)
        .then(response => response.json())
        .then(data => {
            var route = data.routes[0].geometry;

            if (map.getSource('route')) {
                map.getSource('route').setData(route);
            } else {
                map.addLayer({
                    id: 'route',
                    type: 'line',
                    source: {
                        type: 'geojson',
                        data: route
                    },
                    layout: {
                        'line-join': 'round',
                        'line-cap': 'round'
                    },
                    paint: {
                        'line-color': '#3887be',
                        'line-width': 5,
                        'line-opacity': 0.75
                    }
                });
            }
        })
        .catch(error => {
            console.error('Error generating route:', error);
        });        
}