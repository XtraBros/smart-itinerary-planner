// mapboxgl.accessToken = 'pk.eyJ1IjoiYWNla2lsbGVyc2ciLCJhIjoiY2x2MmM5ZXBwMGc3dTJrbGhwemRrNnI0cSJ9.lpqoF8ij6uU3yqWBLKipUA'
mapboxgl.accessToken = 'pk.eyJ1Ijoid2FuZ2Nob25neXU4NiIsImEiOiJjam5qd2FwMmcxNDRwM3FvMzc2aHVmNW5oIn0.4lYyhYClZxVWJXrbho_5hA'

var map = new mapboxgl.Map({
    container: 'map',
    // style: 'mapbox://styles/mapbox/streets-v12',
    style: 'mapbox://styles/wangchongyu86/clp0j9hcy01b301o44qt07gg1',
    // center: [103.8285654153839, 1.24791502223719],
    center: [103.78839388, 1.4042306],
    zoom: 15
});

map.on('load', function() {
    // Define and set bounds for the map
    var bounds = [[103.77861059, 1.39813758], [103.79817716, 1.41032361]];
    map.setMaxBounds(bounds);

    // Add custom tiles
    map.addSource('custom-tiles', {
        type: 'raster',
        tiles: ['http://localhost:3000/tile?url=https://mfamaptilesdev.blob.core.windows.net/tiles/combined-170/{z}/{x}/{y}.png'],
        tileSize: 256,
        minzoom: 12,
        maxzoom: 22
    });
    map.addLayer({
        id: 'custom-tiles-layer',
        type: 'raster',
        source: 'custom-tiles'
    });
});        

function displayRoute(waypoints) {
    // Clear existing routes
    if (map.getSource('route')) {
        map.removeLayer('route');
        map.removeSource('route');
    }

    addMarkers(waypoints)
    var coordinates = waypoints.map(coord => `${coord[0]},${coord[1]}`).join(';');
    var url = `https://api.mapbox.com/directions/v5/mapbox/walking/${coordinates}?geometries=geojson&access_token=${mapboxgl.accessToken}`;

    // Get the route data from Mapbox Directions API
    fetch(url)
        .then(response => response.json())
        .then(data => {
            if (data.routes && data.routes.length > 0) {
                var route = data.routes[0].geometry;

                if (!map.getSource('route')) {
                    map.addSource('route', {
                        'type': 'geojson',
                        'data': {
                            'type': 'Feature',
                            'properties': {},
                            'geometry': route
                        }
                    });
                }
                if (!map.getLayer('route')) {
                    map.addLayer({
                        'id': 'route',
                        'type': 'line',
                        'source': 'route',
                        'layout': {
                            'line-join': 'round',
                            'line-cap': 'round'
                        },
                        'paint': {
                            'line-color': '#ff0000',
                            'line-width': 6
                        }
                    });
                }
            } else {
                console.error('No route found: ', data);
            }
        })
        .catch(err => console.error('Error fetching directions:', err));
}

function submitChat(event) {
    if (event.key === "Enter") {
        event.preventDefault();
        var inputBox = document.getElementById("chatbot-input");
        var message = inputBox.value.trim();

        if (message !== "") {
            var chatMessages = document.getElementById("chatbot-messages");
            postMessage(message, chatMessages);

            inputBox.value = "";
        }
    }
}

function postMessage(message, chatMessages) {
    // Append the visitor's message
    appendMessage("Visitor: " + message, "visitor-message", chatMessages);

    // Send message to Flask endpoint and get the response
    fetch('/ask_plan', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({message: message})
    }).then(response => response.json())
    .then(data => {
        // Append the response
        appendMessage("Guide: " + data.response, "guide-message", chatMessages);
        return fetch('/get_route', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({message: data.response})
        });
    }).then(response => response.json())
    .then(data => {
        get_coordinates(data.response);
    }).catch(error => {
        console.error('Error:', error);
    });
}

function appendMessage(text, className, chatMessages) {
    var messageDiv = document.createElement("div");
    messageDiv.innerHTML = marked.parse(text);
    messageDiv.className = "chat-message " + className;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function get_coordinates(data) {
    let placeNames = data.replace('(', '').replace(')', '').split(',').map(place => place.trim());
    fetch('/get_coordinates', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({places: placeNames})  // Send the list of places to get their coordinates
    })
    .then(response => response.json())
    .then(coordinates => {
        console.log("The coordinates of recommended places: ", coordinates)
        let waypoints = coordinates.map(coord => [coord.lng, coord.lat]);
        displayRoute(waypoints);
    })
    .catch(error => console.error('Error fetching coordinates:', error));
}

function addMarkers(waypoints) {
    if (window.mapMarkers) {
        window.mapMarkers.forEach(marker => marker.remove());
    }
    window.mapMarkers = [];

    waypoints.forEach(coord => {
        var marker = new mapboxgl.Marker()
            .setLngLat([coord[0], coord[1]])
            .addTo(map);
        window.mapMarkers.push(marker);
    });
}