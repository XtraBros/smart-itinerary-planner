var map = L.map('map').setView([1.404402126648088, 103.79302299630343], 17);
L.tileLayer('https://api.mapbox.com/styles/v1/{id}/tiles/{z}/{x}/{y}?access_token={accessToken}', {
    attribution: 'Map data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, ' +
                'Imagery © <a href="https://www.mapbox.com/">Mapbox</a>',
    maxZoom: 18,
    id: 'mapbox/streets-v11',
    tileSize: 512,
    zoomOffset: -1,
    accessToken: 'pk.eyJ1IjoiYWNla2lsbGVyc2ciLCJhIjoiY2x2MmM5ZXBwMGc3dTJrbGhwemRrNnI0cSJ9.lpqoF8ij6uU3yqWBLKipUA'}).addTo(map);

var routingControl = null;

// Function to handle route display
function displayRoute(start, end) {
    if (routingControl) {
        map.removeControl(routingControl); // Remove the existing route, if any
    }
    routingControl = L.Routing.control({
        waypoints: [
            L.latLng(start[0], start[1]),
            L.latLng(end[0], end[1])
        ],
        router: L.Routing.mapbox('pk.eyJ1IjoiYWNla2lsbGVyc2ciLCJhIjoiY2x2MmM5ZXBwMGc3dTJrbGhwemRrNnI0cSJ9.lpqoF8ij6uU3yqWBLKipUA', {profile: 'mapbox/walking'}),
        lineOptions: {
            styles: [{color: '#06f', opacity: 1, weight: 5}]
        },
        routeWhileDragging: true
    }).addTo(map);
}

document.getElementById('routeForm').addEventListener('submit', function(event) {
    event.preventDefault(); // Prevent form from submitting normally
    var input = document.getElementsByName('coordinates')[0].value;

    var waypoints = input.split(';').map(function(pair) {
        var coords = pair.split(',').map(Number);
        return L.latLng(coords[0], coords[1]);
    });

    displayRoute(waypoints);
});

function displayRoute(waypoints) {
    if (routingControl) {
        map.removeControl(routingControl); // Remove the existing route, if any
    }
    
    routingControl = L.Routing.control({
        waypoints: waypoints,
        router: L.Routing.mapbox('pk.eyJ1IjoiYWNla2lsbGVyc2ciLCJhIjoiY2x2MmM5ZXBwMGc3dTJrbGhwemRrNnI0cSJ9.lpqoF8ij6uU3yqWBLKipUA', {profile: 'mapbox/walking'}),
        lineOptions: {
            styles: [{color: '#06f', opacity: 1, weight: 5}]
        },
        routeWhileDragging: true
    }).addTo(map);
}

function isValidCoordinate(coord) {
    return coord.length === 2 && !isNaN(coord[0]) && !isNaN(coord[1]) && Math.abs(coord[0]) <= 90 && Math.abs(coord[1]) <= 180;
}

function submitChat(event) {
    if (event.key === "Enter") {
        event.preventDefault();  // Prevent form submission if it's part of a form.
        var inputBox = document.getElementById("chatbot-input");
        var message = inputBox.value.trim();

        if (message !== "") {
            var chatMessages = document.getElementById("chatbot-messages");
            postMessage(message, chatMessages);

            inputBox.value = ""; // Clear the input field after sending the message
        }
    }
}

function postMessage(message, chatMessages) {
    // Append the visitor's message
    appendMessage("Visitor: " + message, "visitor-message", chatMessages);

    // Send message to Flask and get the response
    fetch('/ask_plan', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({message: message})
    }).then(response => response.json())
    .then(data => {
        // Append the guide's response
        appendMessage("Guide: " + data.response, "guide-message", chatMessages);
        return fetch('/get_route', { // Send the response to another endpoint for further processing
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

    // Auto scroll to the latest message
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function get_coordinates(data) {
    let placeNames = data.replace('(', '').replace(')', '').split(',').map(place => place.trim());
    console.log(JSON.stringify({places: placeNames}));  // Log the data being sent
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
        let waypoints = coordinates.map(coord => L.latLng(coord.lat, coord.lng));
        displayRoute(waypoints);
    })
    .catch(error => console.error('Error fetching coordinates:', error));
}