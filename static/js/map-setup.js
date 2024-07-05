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
        // base url for maptiles
        // ‘tiles’: [‘https://mfamaptilesdev.blob.core.windows.net/tiles/combined-170/{z}/{x}/{y}.png’],
        // use proxy server to get tiles
        tiles: ['https://corsproxy.io/?https://mfamaptilesdev.blob.core.windows.net/tiles/combined-170/{z}/{x}/{y}.png'],
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
    // user location control
    map.addControl(
        new mapboxgl.GeolocateControl({
            positionOptions: {
                enableHighAccuracy: true
            },
            // When active the map will receive updates to the device's location as it changes.
            trackUserLocation: true,
            // Draw an arrow next to the location dot to indicate which direction the device is heading.
            showUserHeading: true
        })
    );
});        

function displayRoute(placeNames, rawCoordinates) {
    return new Promise((resolve, reject) => {
        // Clear existing routes
        if (map.getSource('route')) {
            map.removeLayer('route');
            map.removeLayer('directions');
            map.removeSource('route');
        }
        addMarkers(placeNames, rawCoordinates);
        console.log(rawCoordinates)

        // Check number of waypoints. If less than 25, execute the usual. Else, fetch centroids.
        let fetchDirectionsPromise;
        if (rawCoordinates.length <= 21) {
            const coordinates = rawCoordinates.map(coord => coord.join(',')).join(';');
            var url = `https://api.mapbox.com/directions/v5/mapbox/walking/${coordinates}?geometries=geojson&steps=true&access_token=${mapboxgl.accessToken}`;
            console.log(url)
            // Fetch directions data from Mapbox Directions API
            fetchDirectionsPromise = fetch(url)
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Failed to fetch route data');
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.routes && data.routes.length > 0) {
                        var legs = data.routes[0].legs;
                        var route = data.routes[0].geometry;
                        return { legs, route };
                    } else {
                        console.error('No route found: ', data);
                        throw new Error('No route found');
                    }
                });
        } else {
            // Fetch centroids from Flask endpoint
            fetchDirectionsPromise = fetch("/get_centroids", {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ names: placeNames })
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                const centroids = data.centroids.map(coord => JSON.parse(coord.replace(/\[(\d+\.\d+),(\d+\.\d+)\]/, '[$1,$2]'))).map(coord => coord.join(',')).join(';');
                console.log(centroids)
                // Create a new URL with the returned coordinates
                var newUrl = `https://api.mapbox.com/directions/v5/mapbox/walking/${centroids}?geometries=geojson&steps=true&access_token=${mapboxgl.accessToken}`;
                console.log(newUrl);
                return fetch(newUrl)
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Failed to fetch route data');
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.routes && data.routes.length > 0) {
                        var legs = data.routes[0].legs;
                        var route = data.routes[0].geometry;
                        return { legs, route };
                    } else {
                        console.error('No route found: ', data);
                        throw new Error('No route found');
                    }
                });
            })
            .catch(error => {
                console.error('There was a problem with the fetch operation:', error);
                throw error;
            });
        }

        // Process fetched directions data or centroids
        fetchDirectionsPromise
            .then(result => {
                if (result.legs && result.route) {
                    // Add route to map
                    if (!map.getSource('route')) {
                        map.addSource('route', {
                            'type': 'geojson',
                            'data': {
                                'type': 'Feature',
                                'properties': {},
                                'geometry': result.route
                            }
                        });
                    }

                    if (!map.getLayer('route')) {
                        // Add arrows to the route using static png asset
                        const url = 'static/icons/arrow2.png';
                        map.loadImage(url, function(err, image) {
                            if (err) {
                                console.error('Error loading image:', err);
                                reject(err);
                            }
                            map.addImage('arrow', image);
                        });

                        // Add arrow-line layer
                        map.addLayer({
                            'id': 'route',
                            'type': 'line',
                            'source': 'route',
                            'layout': {
                                'line-join': 'round',
                                'line-cap': 'round',
                            },
                            'paint': {
                                'line-color': '#E21B1B',
                                'line-width': 10,
                                'line-offset': 2,
                                'line-opacity': 0.9,
                                'line-pattern': 'arrow'
                            }
                        });

                        // Update route data on map
                        directions.on('route', function(e) {
                            const route = e.route[0].geometry;
                            map.getSource('route').setData(route);
                        });
                    }

                    // Extract route instructions
                    var instructions = extractRouteInstructions(result.legs, placeNames);
                    resolve(instructions);
                } else if (result.newUrl) {
                    // Handle URL for later use case
                    resolve(result.newUrl);
                } else {
                    throw new Error('Invalid data received');
                }
            })
            .catch(error => {
                console.error('Error processing route or centroids:', error);
                reject(error);
            });
    });
}


// Function to fetch the route for a batch of waypoints
function fetchRouteForBatch(batch) {
    return new Promise((resolve, reject) => {
        var coordinates = batch.map(coord => `${coord[0]},${coord[1]}`).join(';');
        var url = `https://api.mapbox.com/directions/v5/mapbox/walking/${coordinates}?geometries=geojson&steps=true&access_token=${mapboxgl.accessToken}`;
        
        fetch(url)
            .then(response => response.json())
            .then(data => {
                if (data.routes && data.routes.length > 0) {
                    resolve(data.routes[0]);
                } else {
                    reject('No route found');
                }
            })
            .catch(err => reject(err));
    });
}
// Function to optimize route. Takes in list of places and coordinates, returns both ordered in sequence of visit
async function optimizeRoute(placeNames, coordinates) {
    // Check if inputs are valid
    if (!Array.isArray(placeNames) || !Array.isArray(coordinates) || placeNames.length !== coordinates.length) {
        console.log(placeNames);
        console.log(coordinates);
        throw new Error("Invalid inputs. Both inputs should be arrays of the same length.");
    }
    // Get the optimized coordinates
    const coordSequence = await optimizeCoordinates(placeNames,coordinates);
    // Check if optimization was successful
    if (!coordSequence) {
        throw new Error("Optimization failed");
    }
    // Reorder place names according to the optimized coordinates
    // Create a new array to hold the reordered elements
    let optimizedPlaceNames = new Array(coordSequence.length);
    let optimizedCoordinates = new Array(coordSequence.length);

    // Place each element at the position specified by the corresponding index
    for (let i = 0; i < coordSequence.length; i++) {
        optimizedPlaceNames[i] = placeNames[coordSequence[i]];
        optimizedCoordinates[i] = coordinates[coordSequence[i]];
    }
    //console.log(placeNames)
    //console.log(optimizedPlaceNames)
    // Return the result as a nested list
    return [optimizedPlaceNames, optimizedCoordinates];
}

// Function to optimize coordinates. should reorder coordinates in optimised order.
async function optimizeCoordinates(placeNames, coordinates) {
    try {
        //post data to server endpoint
        const response = await fetch('/optimize_route', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({'placeNames': placeNames})
        });

        if (!response.ok) {
            throw new Error('Network response was not ok');
        }

        const coordSequence = await response.json();
        return coordSequence;
    } catch (error) {
        console.error('Error optimizing coordinates:', error);
        return null;
    }
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

async function postMessage(message, chatMessages) {
    // Append the visitor's message
    appendMessage("Visitor: " + message, "visitor-message", chatMessages);
    try {
        // Send message to Flask endpoint and get the response
        let response = await fetch('/ask_plan', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: message })
        });
        if (!response.ok) {
            throw new Error('Network response was not ok ' + response.statusText);
        }
        let data = await response.json();
        // Get the route from the get_coordinates function
        let orderOfVisit = await get_coordinates(data.response, chatMessages);
        let route = orderOfVisit[0][0];
        let instr = orderOfVisit[1];
        // Send a request to the /get_text endpoint with the route
        let textResponse = await fetch('/get_text', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ route: route })
        });
        if (!textResponse.ok) {
            throw new Error('Network response was not ok ' + textResponse.statusText);
        }
        let textData = await textResponse.json();
        // Append the response from the /get_text endpoint to the chat
        appendMessage("Guide: " + textData.response, "guide-message", chatMessages);
        attachEventListeners();
        appendMessage(instr, "nav-button", chatMessages)
    } catch (error) {
        console.error('Error:', error);
    }
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
            showNavSteps(text, messageDiv);
            button.style.display = 'None';
        });

        messageDiv.appendChild(buttonDiv);
    } catch (error) {
        console.error('Error loading button template:', error);
    }
}

function extractRouteInstructions(data, placeNames) {
    let result = '';
  
    // Helper function to find steps in a nested object
    function findSteps(obj) {
      let steps = [];
  
      function recurse(currentObj) {
        for (let key in currentObj) {
          if (key === 'steps') {
            steps = steps.concat(currentObj[key]);
          } else if (typeof currentObj[key] === 'object' && currentObj[key] !== null) {
            recurse(currentObj[key]);
          }
        }
      }
  
      recurse(obj);
      return steps;
    }
  
    // Fetch all steps from the nested dictionary
    const steps = findSteps(data);
  
    // Initialize a counter for placeNames
    let placeIndex = 0;
    let stepIndex = 0;
  
    // Iterate over each step to format the instruction
    steps.forEach((step) => {
      let instruction = step.maneuver.instruction;
      const distance = step.distance.toFixed(0); // format distance to 2 decimal places
  
      // Check if the distance is 0.00, indicating arrival at a destination
      if (parseFloat(distance) === 0 && placeIndex < placeNames.length) {
        instruction = `You have arrived at destination number ${placeIndex}.`;
        result += `<p>${instruction}</p>`;
        placeIndex++; // Move to the next place name
      } else {
        result += `<p>Step ${stepIndex + 1}: ${instruction} (Distance: ${distance} meters)</p>`;
        stepIndex++;
      }
    });
  
    return result;
  }

function showNavSteps(content, messageDiv) {
    // Create modal structure
    var modal = document.getElementById("nav-steps");

    var modalContent = document.createElement("div");
    modalContent.className = "modal-content";

    var closeButton = document.createElement("span");
    closeButton.className = "close";
    closeButton.innerHTML = "&times;";
    closeButton.onclick = function() {
        modal.style.display = "none";
        var button = document.getElementById("nav-button");
        button.style.display = "block";

    };

    var modalText = document.createElement("div");
    modalText.innerHTML = content;

    modalContent.appendChild(closeButton);
    modalContent.appendChild(modalText);
    modal.replaceChildren(modalContent);

    // Append modal to chat box
    messageDiv.appendChild(modal);

    // Display the modal
    modal.style.display = "block";

    // Close the modal when clicking outside of it
    window.onclick = function(event) {
        if (event.target == modal) {
            modal.style.display = "none";
        }
    };
}

async function get_coordinates(data, chatMessages) {
    let placeNames = data.replace('[', '').replace(']', '').split(',').map(place => place.trim());

    try {
        let response = await fetch('/get_coordinates', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ places: placeNames })  // Send the list of places to get their coordinates
        });

        if (!response.ok) {
            throw new Error('Network response was not ok ' + response.statusText);
        }

        let coordinates = await response.json();
        let waypoints = coordinates.map(coord => [coord.lng, coord.lat]);

        // Optimize the route: input: (placeNames, waypoints) output: re-ordered version of input in sequence of visit
        let orderOfVisit = await optimizeRoute(placeNames, waypoints);

        let instr = await displayRoute(orderOfVisit[0], orderOfVisit[1]);
        return [orderOfVisit, instr]
    } catch (error) {
        console.error('Error fetching coordinates:', error);
    }
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
                if (!coord || coord.length !== 2 || isNaN(coord[0]) || isNaN(coord[1])) {
                    console.error(`Invalid coordinates for ${placeName}:`, coord);
                    return; // Skip this iteration if coordinates are invalid
                }
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
            clickMarker(markerId);
        });
    });
}