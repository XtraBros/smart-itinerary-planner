//mapboxgl.accessToken = 'pk.eyJ1IjoiYWNla2lsbGVyc2ciLCJhIjoiY2x2MmM5ZXBwMGc3dTJrbGhwemRrNnI0cSJ9.lpqoF8ij6uU3yqWBLKipUA'
mapboxgl.accessToken = 'pk.eyJ1Ijoid2FuZ2Nob25neXU4NiIsImEiOiJjam5qd2FwMmcxNDRwM3FvMzc2aHVmNW5oIn0.4lYyhYClZxVWJXrbho_5hA'

var waypoints = [];

var map = new mapboxgl.Map({
    container: 'map',
    //style: 'mapbox://styles/mapbox/streets-v12',
    style: 'mapbox://styles/wangchongyu86/clp0j9hcy01b301o44qt07gg1',
    //center: [103.8285654153839, 1.24791502223719],
    center: [103.78839388, 1.4042306],
    zoom: 15
});

const directions = new MapboxDirections({
    accessToken: mapboxgl.accessToken,
    unit: 'metric',
    profile: 'mapbox/walking'
 });
// variable to allow resizing function
window.mapboxMap = map;
map.on('load', function() {
    // Define and set bounds for the map
    var bounds = [[103.77861059, 1.39813758], [103.79817716, 1.41032361]];
    map.setMaxBounds(bounds);

    // Add custom tiles
    map.addSource('custom-tiles', {
        type: 'raster',
        // enable proxy server to get tiles
        tiles: ['http://localhost:3000/tile?url=https://mfamaptilesdev.blob.core.windows.net/tiles/combined-170/{z}/{x}/{y}.png'],
        // using open source map to get tiles without proxy
        //tiles: ['https://a.tile.openstreetmap.org/{z}/{x}/{y}.png'],
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

function displayRoute(placeNames,waypoints, chatMessages) {
    // Clear existing routes
    if (map.getSource('route')) {
        map.removeLayer('route');
        map.removeLayer('directions')
        map.removeSource('route');
    }
    addMarkers(placeNames,waypoints);
    var coordinates = waypoints.map(coord => `${coord[0]},${coord[1]}`).join(';');
    var url = `https://api.mapbox.com/directions/v5/mapbox/walking/${coordinates}?geometries=geojson&steps=true&access_token=${mapboxgl.accessToken}`;

    // Get the route data from Mapbox Directions API
    fetch(url)
        .then(response => response.json())
        .then(data => {
            if (data.routes && data.routes.length > 0) {
                var legs = data.routes[0].legs[0].steps;
                // create function to send legs to detailed display.
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
                            'line-color': '#E21B1B',
                            'line-width': 5,
                            'line-opacity': 0.9
                        }
                    });
                    // Add arrows to the route using static png asset
                    const url = 'static/icons/arrow.png';
                    map.loadImage(url, function(err, image) {
                        if (err) {
                            console.error('err image', err);
                            return;
                        }
                        map.addImage('arrow', image);
                        map.addLayer({
                            'id': 'directions',
                            'type': 'symbol',
                            'source': 'route',
                            'layout': {
                                'symbol-placement': 'line',
                                'symbol-spacing': 1,
                                'icon-allow-overlap': true,
                                // 'icon-ignore-placement': true,
                                'icon-image': 'arrow',
                                'icon-size': 0.06,
                                'visibility': 'visible'
                            },
                            minzoom: 10,
                        });
                    });
                    directions.on('route', function(e) {
                        const route = e.route[0].geometry;
                        map.getSource('route').setData(route);
                    });
                }
            } else {
                console.error('No route found: ', data);
            }
            // // Create a Blob from the JSON string
            // const blob = new Blob([JSON.stringify(legs,null,2)], { type: 'application/json' });

            // // Create a link element
            // const link = document.createElement('a');

            // // Create a URL for the Blob and set it as the href attribute
            // link.href = URL.createObjectURL(blob);

            // // Set the download attribute to specify the file name
            // link.download = 'output.json';

            // // Append the link to the document body
            // document.body.appendChild(link);

            // // Programmatically click the link to trigger the download
            // link.click();
            var instr = extractRouteInstructions(legs)
            // Post detailed route info in chat:
            appendMessage(instr, "nav-button", chatMessages) 
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
    console.log('Visitor message log.')
    appendMessage("Visitor: " + message, "visitor-message", chatMessages);

    // Send message to Flask endpoint and get the response
    fetch('/ask_plan', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({message: message})
    }).then(response => response.json())
    // .then(data => {
    //     // Append the response
    //     appendMessage("Guide: " + data.response, "guide-message", chatMessages);
    //     return fetch('/get_route', {
    //         method: 'POST',
    //         headers: {
    //             'Content-Type': 'application/json'
    //         },
    //         body: JSON.stringify({message: data.response})
    //     });
    // }).then(response => response.json())
    .then(data => {
        console.log('Guide response log.')
        appendMessage("Guide: " + data.response[0], "guide-message", chatMessages);
        get_coordinates(data.response[1], chatMessages);
    }).catch(error => {
        console.error('Error:', error);
    });
}

// creaate template and styles for each visitor/guide message.
function appendMessage(text, className, chatMessages) {
    var messageDiv = document.createElement("div");
    if (className == "nav-button"){
        loadButtonTemplate(messageDiv,text)
    } else {
        messageDiv.innerHTML = marked.parse(text);
        messageDiv.className = "chat-message " + className;      
    }
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

}

async function loadButtonTemplate(messageDiv, text) {
    try {
        const response = await fetch('static/html/nav-button.html');
        const template = await response.text();
        const buttonDiv = document.createElement("div");
        buttonDiv.innerHTML = template;

        const button = buttonDiv.querySelector("button");
        button.addEventListener("click", function() {
            showModal(text);
        });

        messageDiv.appendChild(buttonDiv);
    } catch (error) {
        console.error('Error loading button template:', error);
    }
}

function extractRouteInstructions(data) {
    let result = '';
  
    data.forEach((step, stepIndex) => {
        const instruction = step.maneuver.instruction;
        const distance = step.distance.toFixed(2); // format distance to 2 decimal places
        result += `<p>Step ${stepIndex + 1}: ${instruction} (Distance: ${distance} meters)</p>`;
    });
  
    return result;
}

function showModal(content) {
    // Create modal structure
    var modal = document.getElementById("modal");

    var modalContent = document.createElement("div");
    modalContent.className = "modal-content";

    var closeButton = document.createElement("span");
    closeButton.className = "close";
    closeButton.innerHTML = "&times;";
    closeButton.onclick = function() {
        modal.style.display = "none";
    };

    var modalText = document.createElement("div");
    modalText.innerHTML = content;

    modalContent.appendChild(closeButton);
    modalContent.appendChild(modalText);
    modal.replaceChildren(modalContent);

    // Append modal to chat box
    var chatBox = document.getElementById("chatbot-area");
    chatBox.appendChild(modal);

    // Display the modal
    modal.style.display = "block";

    // Close the modal when clicking outside of it
    window.onclick = function(event) {
        if (event.target == modal) {
            modal.style.display = "none";
        }
    };
}

function get_coordinates(data,chatMessages) {
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
        displayRoute(placeNames,waypoints,chatMessages);
    })
    .catch(error => console.error('Error fetching coordinates:', error));
}

function addMarkers(placeNames, waypoints) {
    if (window.mapMarkers) {
        for (const [key, value] of Object.entries(window.mapMarkers)) {
            value.remove();
        }
    }
    window.mapMarkers = {};

    fetchPlacesData(placeNames).then(placesData => {
        fetchTemplate('static/html/info-card.html').then(template => {
            var parser = new DOMParser();

            placeNames.forEach((placeName, index) => {
                var coord = waypoints[index];
                placeName = placeName.replace(/['\[\]]/g, '');

                var place = {
                    description: placesData[placeName],
                    name: placeName,
                };

                var name = placeName.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '');
                place.thumbnail = `/static/thumbnails/${name}.jpg`;

                var popupContentString = populateTemplate(template, place);
                var doc = parser.parseFromString(popupContentString, 'text/html');
                var popupContent = doc.querySelector('.info-card-content');
                var popupId = placeName.replace(/\s+/g, '-').toLowerCase();


                var popup = new mapboxgl.Popup().setDOMContent(popupContent);

                var marker = new mapboxgl.Marker()
                    .setLngLat([coord[0], coord[1]])
                    .setPopup(popup)
                    .addTo(map);

                window.mapMarkers[popupId] = marker;  // Store marker by ID
            });
            attachEventListeners();
        });
    });
}

function fetchTemplate(url) {
    return fetch(url).then(response => response.text());
}

function populateTemplate(template, data) {
    return template.replace(/{{(\w+)}}/g, (match, key) => data[key] || '');
}
// function to get places data.
function fetchPlacesData(places) {
    return fetch('/place_info', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ places: places })
    })
    .then(response => response.json())
    .catch(error => {
        console.error('Error fetching places data:', error);
    });
}

// Zoom button scripts
document.getElementById('zoom-in').addEventListener('click', () => {
    map.zoomIn();
});

document.getElementById('zoom-out').addEventListener('click', () => {
    map.zoomOut();
});
// Function to simulate click on marker to show popup
function clickMarker(markerId) {
    console.log(`Clicking marker for ${markerId}`);
    if (window.mapMarkers[markerId]) {
        window.mapMarkers[markerId].togglePopup();
    }
}

// Add event listeners to the links
function attachEventListeners() {
    document.querySelectorAll('.location-link').forEach(function(link) {
        link.addEventListener('mouseover', function() {
            var markerId = this.getAttribute('data-marker-id');
            clickMarker(markerId);
        });

        link.addEventListener('mouseout', function() {
            var markerId = this.getAttribute('data-marker-id');
            clickMarker(markerId);  // Toggling the popup off
        });
    });
}