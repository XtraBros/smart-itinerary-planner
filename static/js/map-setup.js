mapboxgl.accessToken = 'pk.eyJ1IjoiYWNla2lsbGVyc2ciLCJhIjoiY2x2MmM5ZXBwMGc3dTJrbGhwemRrNnI0cSJ9.lpqoF8ij6uU3yqWBLKipUA'

var map = new mapboxgl.Map({
    container: 'map',
    style: 'mapbox://styles/mapbox/streets-v12',
    center: [103.8285654153839, 1.24791502223719],
    zoom: 14
});

function displayRoute(waypoints) {
    // Clear existing routes
    if (map.getSource('route')) {
        map.removeLayer('route');
        map.removeSource('route');
    }

    addMarkers(waypoints)

    // Get optimized trips from Mapbox Optimization API
    var coordinates = waypoints.map(coord => `${coord[0]},${coord[1]}`).join(';');
    var url = `https://api.mapbox.com/optimized-trips/v1/mapbox/walking/${coordinates}?geometries=geojson&source=first&destination=last&roundtrip=false&access_token=${mapboxgl.accessToken}`;

    // Get the route data from Mapbox Directions API
    fetch(url)
        .then(response => response.json())
        .then(data => {
            var route = data.trips[0].geometry;

            map.addSource('route', {
                'type': 'geojson',
                'data': {
                    'type': 'Feature',
                    'properties': {},
                    'geometry': route
                }
            });
            map.addLayer({
                'id': 'route',
                'type': 'line',
                'source': 'route',
                'layout': {
                    'line-join': 'round',
                    'line-cap': 'round'
                },
                'paint': {
                    'line-color': '#ff7e5f',
                    'line-width': 6
                }
            });
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
    messageDiv.textContent = text;
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