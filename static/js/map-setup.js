// Fetch the access token from the Flask endpoint and initialize the map
var waypoints = [];
var map;
var directions;
let route = {};
let navigationEnabled = false;
let simulationRunning = false; // Flag to indicate if the simulation is running
let simulationPaused = false;  // Flag to indicate if the simulation is paused
let simulationTimeout;         // Variable to store the timeout ID
let userMarker;
let userLocation;

window.onload = function () {
    navigator.geolocation.getCurrentPosition((position) => {
        // 1.253142,103.8261829
        userLocation = {
            lng: '103.827973',
            lat: '1.250277'
        };
        console.log(`User location updated to: ${userLocation.lat}, ${userLocation.lng}`);
    }, (error) => {
        console.error('Error obtaining geolocation:', error);
    });
}

const geolocateControl = new mapboxgl.GeolocateControl({
    positionOptions: {
        enableHighAccuracy: true
    },
    trackUserLocation: false,
    showUserHeading: true
});

fetch('/config')
    .then(response => response.json())
    .then(data => {
        // Assuming the response contains a JSON object with an 'accessToken' property
        mapboxgl.accessToken = data.config.MAPBOX_ACCESS_TOKEN;

        map = new mapboxgl.Map({
            container: 'map',
            style: 'mapbox://styles/mapbox/streets-v12',
            //style: 'mapbox://styles/wangchongyu86/clp0j9hcy01b301o44qt07gg1',
            //center: [103.8285654153839, 1.24791502223719],
            center: [103.827973, 1.250277],
            zoom: 14
        });

        directions = new MapboxDirections({
            accessToken: mapboxgl.accessToken,
            unit: 'metric',
            profile: 'mapbox/walking'
        });
        // variable to allow resizing function
        window.mapboxMap = map;
        map.on('load', function() {
            // Define and set bounds for the map
            // var bounds = [[103.77861059, 1.39813758], [103.79817716, 1.41032361]];
            // map.setMaxBounds(bounds);

            // Add custom tiles
            // map.addSource('custom-tiles', {
            //     type: 'raster',
            //     // base url for maptiles
            //     // ‘tiles’: [‘https://mfamaptilesdev.blob.core.windows.net/tiles/combined-170/{z}/{x}/{y}.png’],
            //     // use proxy server to get tiles
            //     tiles: [data.config.MAPBOX_MAPTILES],
            //     // using open source map to get tiles without proxy
            //     //tiles: ['https://a.tile.openstreetmap.org/{z}/{x}/{y}.png'],
            //     tileSize: 256,
            //     // minzoom: 12,
            //     // maxzoom: 22,
            //     attribution: '© OpenStreetMap contributors'
            // });
            // map.addLayer({
            //     id: 'custom-tiles-layer',
            //     type: 'raster',
            //     source: 'custom-tiles'
            // });
            // 3D Layer for navigation view.    
            map.addLayer({
                'id': '3d-buildings',
                'source': 'composite',
                'source-layer': 'building',
                'filter': ['==', 'extrude', 'true'],
                'type': 'fill-extrusion',
                'minzoom': 15,
                'paint': {
                    'fill-extrusion-color': [
                        'interpolate',
                        ['linear'],
                        ['zoom'],
                        15, '#aaa',
                        16, '#aaa'
                    ],
                    'fill-extrusion-height': [
                        'interpolate', ['linear'], ['zoom'],
                        15, 0,
                        16, ['get', 'height']
                    ],
                    'fill-extrusion-base': [
                        'interpolate', ['linear'], ['zoom'],
                        15, 0,
                        16, ['get', 'min_height']
                    ],
                    'fill-extrusion-opacity': 0.6,
                    'fill-extrusion-vertical-gradient': true // This gives the buildings a gradient similar to the default style
                }
            });
            
            // user location control
            // Add the Geolocate Control to the map
            map.addControl(geolocateControl);

            // Override the geolocate event to use navigator.geolocation
            geolocateControl.on('geolocate', () => {
                navigator.geolocation.getCurrentPosition((position) => {
                    userLocation = {
                        lng: position.coords.longitude,
                        lat: position.coords.latitude
                    };
                    // Set the user's location on the map
                    map.flyTo({
                        center: [userLocation.lng, userLocation.lat],
                        essential: true // this animation is considered essential with respect to prefers-reduced-motion
                    });
                    console.log(`User location updated to: ${userLocation.lat}, ${userLocation.lng}`);
                }, (error) => {
                    console.error('Error obtaining geolocation:', error);
                });
            });
        });
    })
    .catch(error => {
        console.error('Error fetching the access token:', error);
    });

// Navigation Mode 
function enableNavigationMode(route, instructions) {
    document.getElementById('popupModal').style.display = "none";
    let currentStepIndex = 0; // Start at the first step of the route

    // Function to update navigation instructions based on user's current location
    function updateNavigationInstructions(userLocation) {
        // Calculate the distance between the user's current location and the next checkpoint
        const checkpoint = {
            lng: route.coordinates[currentStepIndex][0],
            lat: route.coordinates[currentStepIndex][1]
        };        
        console.log(checkpoint)
        const distanceToCheckpoint = calculateDistance(userLocation, checkpoint);

        // If the user is close enough to the checkpoint, move to the next step
        const thresholdDistance = 10; // meters, adjust this value as needed
        if (distanceToCheckpoint < thresholdDistance) {
            currentStepIndex++;
            if (currentStepIndex < instructions.length) {
                //displayInstruction(instructions[currentStepIndex]);
            } else {
                console.log("You've reached your destination!");
                stopNavigation(); // Optionally stop navigation or handle route completion
            }
        }
    }

    // Function to calculate the distance between two points (Haversine formula)
    function calculateDistance(point1, point2) {
        const R = 6371000; // Radius of the Earth in meters
        const toRad = Math.PI / 180;
        const dLat = (point2.lat - point1.lat) * toRad;
        const dLng = (point2.lng - point1.lng) * toRad;

        const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                  Math.cos(point1.lat * toRad) * Math.cos(point2.lat * toRad) *
                  Math.sin(dLng / 2) * Math.sin(dLng / 2);

        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
    }    

    // Monitor the user's GPS location
    //navigator.geolocation.watchPosition((position) => {
    navigator.geolocation.getCurrentPosition((position) => {
        const userLocation = {
            lng: position.coords.longitude,
            lat: position.coords.latitude
        };
        const userHeading = position.coords.heading || 0;

        // Rotate the map to match the user's heading
        map.rotateTo(userHeading);

        // Update navigation instructions based on the user's location
        updateNavigationInstructions(userLocation);

        // Perform map animations and start simulation in sequence
        function startSimulationAfterAnimation() {
            // Start simulating the user's location along the route
            simulateUserLocation(route);
        }

        // Animate the map to tilt and zoom for 3D perspective
        map.easeTo({
            pitch: 60, // Tilts the map to 60 degrees for a 3D perspective
            zoom: 20,  // Adjust the zoom level for better street view navigation
            center: [userLocation.lng, userLocation.lat], // Center map on user's location
            duration: 500 // Animation duration in milliseconds
        });

        // Wait for easeTo animation to complete, then start simulation
        map.once('moveend', startSimulationAfterAnimation);

    }, (error) => {
        console.error('Error getting user location:', error);
    });
    //, {
    //     enableHighAccuracy: true, // Enable high accuracy mode to use GPS
    //     maximumAge: 0, // Don't use a cached position
    //     timeout: 10000 // Set a timeout for getting the location
    // });
}


function disableNavigationMode() {
    map.easeTo({
        pitch: 0, // Back to 2D top-down view
        bearing: 0,
        zoom: 15, // Adjust zoom level if needed
        duration: 1000
    });
    if (simulationRunning){
        pauseSimulation();
    }
}

// Function to start simulating user location along the route with smooth movement
function simulateUserLocation(route) {
    console.log("Starting simulation");
    let index = 0;
    const targetDistance = 10; // meters per step for interpolation

    // Initialize the user marker if it doesn't exist
    if (!userMarker) {
        userMarker = new mapboxgl.Marker({ color: 'red' })
            .setLngLat([route.coordinates[0][0], route.coordinates[0][1]])
            .addTo(map);
    }

    function updateLocation() {
        if (!simulationRunning) return; // If not running, do nothing

        if (index < route.coordinates.length - 1) {
            // Simulate the user's location along the route
            const currentPosition = {
                lng: route.coordinates[index][0],
                lat: route.coordinates[index][1]
            };
            const nextPosition = {
                lng: route.coordinates[index + 1][0],
                lat: route.coordinates[index + 1][1]
            };

            // Calculate the distance between the current and next position
            const distance = distanceBetweenPoints([currentPosition.lng, currentPosition.lat], [nextPosition.lng, nextPosition.lat]);

            // Animate the marker along the path between current and next position
            function animateMarker(interpolatedPosition) {
                if (!simulationRunning) return; // If not running, do nothing

                // Update marker position
                userMarker.setLngLat(interpolatedPosition);

                // Update the user's location in your app
                updateUserLocation({ lng: interpolatedPosition[0], lat: interpolatedPosition[1] });

                // Calculate remaining distance to next position
                const remainingDistance = distanceBetweenPoints(interpolatedPosition, [nextPosition.lng, nextPosition.lat]);

                // If the remaining distance is less than the target, move to the next point
                if (remainingDistance <= targetDistance) {
                    index++;
                    if (index < route.coordinates.length - 1) {
                        setTimeout(updateLocation, 100); // Continue to the next point
                    } else {
                        console.log("Route simulation completed");
                        simulationRunning = false;
                    }
                } else {
                    // Calculate the new interpolated position
                    const fraction = targetDistance / remainingDistance;
                    const newInterpolatedPosition = interpolate(interpolatedPosition, [nextPosition.lng, nextPosition.lat], fraction);

                    // Continue animating along the current segment
                    setTimeout(() => animateMarker(newInterpolatedPosition), 2000);
                }
            }

            // Start animating along the current segment with initial interpolation
            const initialFraction = targetDistance / distance;
            const initialInterpolatedPosition = interpolate([currentPosition.lng, currentPosition.lat], [nextPosition.lng, nextPosition.lat], initialFraction);
            animateMarker(initialInterpolatedPosition);

        } else {
            console.log("Route simulation completed");
            simulationRunning = false;
        }
    }

    // Start the location simulation
    simulationRunning = true;
    simulationPaused = false;
    updateLocation();
}


// Function to calculate the distance between two points using the Haversine formula
function distanceBetweenPoints(p1, p2) {
    const R = 6371000; // Radius of the Earth in meters
    const toRad = Math.PI / 180;
    const dLat = (p2[1] - p1[1]) * toRad;
    const dLng = (p2[0] - p1[0]) * toRad;

    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(p1[1] * toRad) * Math.cos(p2[1] * toRad) *
              Math.sin(dLng / 2) * Math.sin(dLng / 2);

    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

// Function to interpolate between two points
function interpolate(p1, p2, fraction) {
    return [
        p1[0] + (p2[0] - p1[0]) * fraction,
        p1[1] + (p2[1] - p1[1]) * fraction
    ];
}

// Function to update user location in your app
function updateUserLocation(location) {
    // Update logic here
    console.log("User location updated:", location);
}


// Function to pause the simulation
function pauseSimulation() {
    console.log(route)
    if (simulationRunning && !simulationPaused) {
        simulationPaused = true;
        clearTimeout(simulationTimeout); // Stop the current timeout
        console.log("Simulation paused");
    }
}

// Function to stop the simulation
function stopSimulation() {
    simulationRunning = false;
    simulationPaused = false;
    clearTimeout(simulationTimeout); // Stop any ongoing timeout
    console.log("Simulation stopped");
}


function updateUserLocation(newLocation) {
    userLocation = newLocation;

    // Update the map view to center on the new location
    map.flyTo({
        center: [userLocation.lng, userLocation.lat],
        essential: true, // Animation is essential
        zoom: 18 // Adjust zoom level as needed
    });

    // Update the marker position
    if (userMarker) {
        userMarker.setLngLat([userLocation.lng, userLocation.lat]);
    }
}

function displayRoute(userLocation, placeNames, rawCoordinates) {
    return new Promise((resolve, reject) => {
        // Clear existing routes
        if (map.getSource('route')) {
            map.removeLayer('route');
            map.removeLayer('directions');
            map.removeSource('route');
        }
        addMarkers(placeNames, rawCoordinates);

        // Check number of waypoints. If less than 25, execute the usual. Else, fetch centroids.
        let fetchDirectionsPromise;
        const allCoordinates = [[userLocation.lng, userLocation.lat], ...rawCoordinates];
        console.log(allCoordinates)
        const coordinates = allCoordinates.map(coord => coord.join(',')).join(';');
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
                    route = data.routes[0].geometry;
                    return { legs, route };
                } else {
                    console.error('No route found: ', data);
                    throw new Error('No route found');
                }
            });

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
                map.flyTo({
                    center: [userLocation.lng, userLocation.lat],
                    essential: true, // This ensures the animation happens even with prefers-reduced-motion
                    zoom: 15 // Increase the zoom level as needed
                });
            })
            .catch(error => {
                console.error('Error processing route or centroids:', error);
                reject(error);
            });
    });
}

// Function to optimize route. Takes in list of places and coordinates, returns both ordered in sequence of visit
async function optimizeRoute(placeNames, coordinates) {
    // Check if inputs are valid
    if (placeNames.length === 1) {
        return [placeNames, coordinates];
    }
    if (!Array.isArray(placeNames) || !Array.isArray(coordinates) || placeNames.length !== coordinates.length) {
        console.log(placeNames);
        console.log(coordinates);
        throw new Error("Invalid inputs. Both inputs should be arrays of the same length.");
    }
    // Get the optimized coordinates
    const coordSequence = await getOptimizedSequence(placeNames);
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
async function getOptimizedSequence(placeNames) {
    console.log(placeNames);
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
        var message = inputBox.value;

        if (message !== "") {
            var chatMessages = document.getElementById("chatbot-messages");
            postMessage(message, chatMessages);

            inputBox.value = "";
        }
    }
}

async function postMessage(message, chatMessages) {
    // Append the visitor's message
    appendMessage(message, "visitor-message", chatMessages);
    try {
        // Send message to Flask endpoint and get the response
        let response = await fetch('/ask_plan', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: message, userLocation: userLocation })
        });
        if (!response.ok) {
            throw new Error('Network response was not ok ' + response.statusText);
        }
        let data = await response.json();
        console.log("GPT response: " + JSON.stringify(data));
        // check for operation type and run route functions if neccesarry.
        if (data.operation == "route"){
            console.log("PLaces: " + data.response);
            let cleanedPlaceNames = data.response;

            console.log(cleanedPlaceNames); // Check the cleaned list
            // Get the route from the get_coordinates function
            let orderOfVisit = await get_coordinates(cleanedPlaceNames);
            let route = orderOfVisit[0][0];
            let instr = orderOfVisit[1];
            // Send a request to the /get_text endpoint with the route
            let textResponse = await fetch('/get_text', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ route: route, message: message })
            });
            if (!textResponse.ok) {
                throw new Error('Network response was not ok ' + textResponse.statusText);
            }
            let textData = await textResponse.json();
            // Append the response from the /get_text endpoint to the chat
            appendMessage(textData.response, "guide-message", chatMessages);
            appendMessage(instr, "nav-button", chatMessages);
            attachEventListeners();
        }else if (data.operation == "location"){
            let cleanedPlaceNames = data.response;

            console.log(cleanedPlaceNames); // Check the cleaned list
            // Get the route from the get_coordinates function
            let orderOfVisit = await get_coordinates_without_route(cleanedPlaceNames);
            // Send a request to the /get_text endpoint with the route
            let textResponse = await fetch('/get_text', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ route: orderOfVisit, message: message })
            });
            if (!textResponse.ok) {
                throw new Error('Network response was not ok ' + textResponse.statusText);
            }
            let textData = await textResponse.json();
            // Append the response from the /get_text endpoint to the chat
            appendMessage(textData.response, "guide-message", chatMessages);
            attachEventListeners();
        } else { // return message directly
            appendMessage(data.response, 'guide-message', chatMessages);
        }
    } catch (error) {
        console.error('Error:', JSON.stringify(error));
    }
}

// creaate template and styles for each visitor/guide message.
function appendMessage(text, className, chatMessages) {
    if (className == "nav-button"){
        var messageDiv = document.createElement("div");
        var navButton = document.querySelector(".nav-button");
        if (navButton) {
            navButton.remove();
        }
        loadButtonTemplate(messageDiv,text)
        chatMessages.appendChild(messageDiv);
    } else if (className == "guide-message") {
        chatMessages.innerHTML += `<div class='chat-message ${className}'>
            <div class='guideImage'><img src="static/icons/choml.png" alt="" srcset=""></div>
            <div class='guideText'>${marked.parse(text)}</div>
        </div>
        `
    } else {
        chatMessages.innerHTML += `<div class='chat-message ${className}'>${marked.parse(text)}</div>`
    }
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function loadButtonTemplate(messageDiv, text) {
    try {
        const response = await fetch('static/html/nav-button.html');
        const template = await response.text();
        const buttonDiv = document.createElement("div");
        buttonDiv.innerHTML = template;

        const button = buttonDiv.querySelector("button");
        button.addEventListener('click', function() {
            if (!navigationEnabled) {
                enableNavigationMode(route, text);
                console.log(route)
                this.textContent = 'Exit Navigation Mode';
            } else {
                disableNavigationMode();
                this.textContent = 'Click here to start navigation!';
            }
            navigationEnabled = !navigationEnabled;
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

async function get_coordinates(data) {
    let placeNames = data;
    try {
        // Fetch the user's current location
        userLocation = await new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(
                position => resolve({ 
                    lat: parseFloat(position.coords.latitude), 
                    lng: parseFloat(position.coords.longitude)
                }),
                error => reject(error)
            );
        });

        // Send the place names and the user's location to the Flask endpoint
        let response = await fetch('/get_coordinates', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                places: data,
            })
        });

        if (!response.ok) {
            throw new Error('Network response was not ok ' + response.statusText);
        }

        let responseData = await response.json();
        let coordinates = responseData.coordinates;
        placeNames = responseData.places;

        // Map coordinates to waypoints
        let waypoints = coordinates.map(coord => [coord.lng, coord.lat]);

        // Optimize the route: input: (placeNames, waypoints) output: re-ordered version of input in sequence of visit
        let orderOfVisit = await optimizeRoute(placeNames, waypoints);

        let instr = await displayRoute(userLocation,orderOfVisit[0], orderOfVisit[1]);
        return [orderOfVisit, instr];
    } catch (error) {
        console.error('Error fetching coordinates:', error);
    }
}

async function get_coordinates_without_route(data) {
    let placeNames = data;
    try {
        // Send the place names and the user's location to the Flask endpoint
        let response = await fetch('/get_coordinates', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                places: data,
            })
        });

        if (!response.ok) {
            throw new Error('Network response was not ok ' + response.statusText);
        }

        let responseData = await response.json();
        let coordinates = responseData.coordinates;
        placeNames = responseData.places;

        // Map coordinates to waypoints
        let waypoints = coordinates.map(coord => [coord.lng, coord.lat]);

        // Optimize the route: input: (placeNames, waypoints) output: re-ordered version of input in sequence of visit
        let orderOfVisit = await optimizeRoute(placeNames, waypoints);
        console.log(orderOfVisit);
        if (map.getSource('route')) {
            map.removeLayer('route');
            map.removeLayer('directions');
            map.removeSource('route');
        }
        addMarkers(placeNames, waypoints);
        return orderOfVisit;
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
                console.log(placeName)

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