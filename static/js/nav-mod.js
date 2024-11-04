import { sharedState } from "./main.js";
import { setDottedLine } from "./map-setup.js";

const listButton = document.getElementsByClassName('mapandlistbut')[0]
const dingwenndId = document.getElementById('dingwennd');

export function updateNavigationInstructions(userLocation) {
    const thresholdDistance = 20; // Distance threshold for reaching a checkpoint
    const arrivalThreshold = 5; // Distance threshold for final destination arrival

    // Get current and next checkpoint locations
    const currentCheckpoint = {
        lng: sharedState.steps[sharedState.currentStepIndex].maneuver.location[0],
        lat: sharedState.steps[sharedState.currentStepIndex].maneuver.location[1]
    };

    const nextCheckpoint = sharedState.currentStepIndex + 1 < sharedState.steps.length
        ? {
            lng: sharedState.steps[sharedState.currentStepIndex + 1].maneuver.location[0],
            lat: sharedState.steps[sharedState.currentStepIndex + 1].maneuver.location[1]
        }
        : null; // No next checkpoint if this is the final step

    const distanceToCurrentCheckpoint = calculateDistance(userLocation, currentCheckpoint);

    let increment = false;

    // Check if the user has reached or passed the current checkpoint
    if (distanceToCurrentCheckpoint < thresholdDistance) {
        // If close enough to current checkpoint, increment step
        increment = true;
    } else if (nextCheckpoint) {
        // Calculate distance to next checkpoint
        const distanceToNextCheckpoint = calculateDistance(userLocation, nextCheckpoint);

        // If user is closer to the next checkpoint than the current one, increment step
        if (distanceToNextCheckpoint < distanceToCurrentCheckpoint) {
            increment = true;
        }
    }

    // If increment is true, move to the next step
    if (increment) {
        sharedState.currentStepIndex++;
        console.log("Moving to next checkpoint, step index: " + sharedState.currentStepIndex);
    }
    const finalDestination = {
        lng: sharedState.steps[sharedState.steps.length - 1].maneuver.location[0],
        lat: sharedState.steps[sharedState.steps.length - 1].maneuver.location[1]
    };
    const distanceToFinalDestination = calculateDistance(userLocation, finalDestination);
    if (distanceToFinalDestination <= arrivalThreshold) {
        // Display arrival message and stop further instructions
        console.log("User has arrived at the destination.");
        document.getElementById("distanceText").textContent = "You have arrived at your destination!";
        return;
    }
    // Display current instruction if still within bounds
    if (sharedState.currentStepIndex < instructions.length) {
        const nextInstruction = instructions[sharedState.currentStepIndex].instruction;
        const remainingDist = calculateRemainingDistance(route.coordinates.slice(sharedState.currentStepIndex));
        const modifierType = instructions[sharedState.currentStepIndex].modifier;
        displayInstruction(nextInstruction, distanceToCurrentCheckpoint, remainingDist, modifierType);
    } else {
        // End of route handling, display remaining distance and duration
        const remainingDist = calculateRemainingDistance(route.coordinates.slice(sharedState.currentStepIndex));
        document.getElementById("distanceText").textContent = `${distanceToCurrentCheckpoint.toFixed(1)} metres`;
        document.querySelector('#journeyDistance h3').textContent = (remainingDist / 1000).toFixed(2);
        document.querySelector('#journeyDuration h3').textContent = calculateRemainingDuration(remainingDist, 1.4);
    }
}
//May need to implement different modes : change walking speed.
export function calculateRemainingDuration(remainingDistance, walkingSpeed) {
    // Calculate the remaining duration in seconds
    const remainingDuration = (remainingDistance / walkingSpeed / 60).toFixed(0);

    return remainingDuration;
}
// Function to use user's current location and update their position along the route
export function trackUserLocation(route) {
    console.log("Tracking user location");
    const imgs = pauseAndpaly.getElementsByTagName('img')[0];
    imgs.setAttribute('src', `static/icons/pause.svg`);

    // Set the user's initial location marker at the starting point
    sharedState.walkedRoute.unshift(route.coordinates[0]);
    // Function to handle location updates from the GeolocateControl
    function updateLocation(position) {
        if (!simulationRunning) return;
        const currentPosition = {
            lng: position.coords.longitude,
            lat: position.coords.latitude
        };
        const nextPosition = {
            lng: route.coordinates[sharedState.routeIndex + 1][0],
            lat: route.coordinates[sharedState.routeIndex + 1][1]
        };
        debounce(() => {
            getPoisByLocation(currentPosition);
        }, 5000)
        // Update the user's location in your app
        updateUserLocation(currentPosition);

        // Update the marker position to the user's current location
        // userMarker.setLngLat([currentPosition.lng, currentPosition.lat]);

        // Calculate remaining distance to the next position on the route
        const remainingDistance = calculateDistance([currentPosition.lng, currentPosition.lat], [nextPosition.lng, nextPosition.lat]);

        // updateWalkedRoute([currentPosition.lng, currentPosition.lat]);
        updateRemainingRoute([currentPosition.lng, currentPosition.lat]);

        // If the remaining distance is less than the threshold, move to the next point
        if (remainingDistance <= targetDistance) {
            sharedState.routeIndex++;

            if (sharedState.routeIndex >= route.coordinates.length - 1) {
                // Route completed
                closedNavfun();
                navcompleted.classList.add('fadeshowin');
                pauseAndpaly.style.display = 'none';
                initProperty();
                console.log("Route tracking completed");
            }
        }
    }

    // Event listener for when the user's location changes
    sharedState.geolocateControl.on('geolocate', (position) => {
        // console.log('Updating user location:')
        debounce(() => {
            updateLocation(position);
        }, 100)
    });
}
export function updateWalkedRoute(line) {
    // Add the current position to the walked route
    // walkedRoute.push(currentPosition);

    // Update the map with the walked route
    sharedState.map.getSource('walked-route').setData({
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": sharedState.walkedRoute
        }
    });
}
export function updateRemainingRoute(currentPosition) {
    // Update the remaining route after trimming
    const remainingRoute = route.coordinates.slice(sharedState.routeIndex + 1);
    remainingRoute.unshift(currentPosition);
    sharedState.map.getSource('route').setData({
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": remainingRoute
        }
    });
}
// Function to calculate the distance between two points (Haversine formula)
export function calculateDistance(point1, point2) {
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
export function updateUserLocation(location) {
    userLocation = location;
    // console.log("User location updated:", location);  // Disabled for frequency control
    // Function to update user location in your app
    let lastRecalculationTime = 0;  // Track the last time the route was recalculated
    const recalculationDelay = 5000; // Set a delay (e.g., 5000ms = 5 seconds)
    const currentTime = Date.now(); // Get the current time in milliseconds

    // Check if enough time has passed since the last recalculation
    if (currentTime - lastRecalculationTime >= recalculationDelay) {
        // Check if the user is off-route
        if (isUserOffRoute(location, route).distance > 30 && sharedState.endPlaceProt) {
            console.log('User is off-route, recalculating route...');
            recalculateRoute(location, sharedState.endPlaceProt);  // Call reroute function
            lastRecalculationTime = currentTime;  // Update the last recalculation time
        }
    }
}
// Function to optimize route. Takes in list of places and coordinates, returns both ordered in sequence of visit
export async function optimizeRoute(placeNames, coordinates) {
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
export async function getOptimizedSequence(placeNames, chatMessages) {
    console.log(placeNames);
    try {
        // Post data to server endpoint
        const response = await fetch('/optimize_route', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 'placeNames': placeNames })
        });

        if (!response.ok) {
            appendMessage({
                text: 'It seems my network connection with you is unstable. Please try sending me your message again.', chatMessages, type: 'message',
            });
            throw new Error('Network response was not ok');
        }

        const coordSequence = await response.json();

        // Check if the response contains a message key, indicating an error
        if (coordSequence.message) {
            appendMessage({ text: coordSequence.message, chatMessages, type: 'message' });
            return;
        }

        return coordSequence;
    } catch (error) {
        console.error('Error optimizing coordinates:', error);

        // Display a generic error message using appendMessage
        return;
    }
}
export function extractRouteInstructions(data, placeNames) {
    let result = '';

    // Helper function to find steps in a nested object
    function findSteps(obj) {
        let stepslist = [];

        function recurse(currentObj) {
            for (let key in currentObj) {
                if (key === 'steps') {
                    stepslist = stepslist.concat(currentObj[key]);
                } else if (typeof currentObj[key] === 'object' && currentObj[key] !== null) {
                    recurse(currentObj[key]);
                }
            }
        }

        recurse(obj);
        return stepslist;
    }

    // Fetch all steps from the nested dictionary
    const stepslist = findSteps(data);

    // Initialize a counter for placeNames
    let placeIndex = 0;
    let stepIndex = 0;

    // Iterate over each step to format the instruction
    stepslist.forEach((step) => {
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
export function showNavSteps(content, messageDiv) {
    // Create modal structure
    var modal = document.getElementById("nav-steps");

    var modalContent = document.createElement("div");
    modalContent.className = "modal-content";

    var closeButton = document.createElement("span");
    closeButton.className = "close";
    closeButton.innerHTML = "&times;";
    closeButton.onclick = function () {
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
    window.onclick = function (event) {
        if (event.target == modal) {
            modal.style.display = "none";
        }
    };
}
export function getInstructions(data) {
    const instructions = [];

    data.forEach(step => {
        // Extract maneuver details
        const maneuver = step.maneuver || {};
        const instruction = maneuver.instruction || "";
        const typeOfManeuver = maneuver.type || "";
        const bearingBefore = maneuver.bearing_before || "";
        const bearingAfter = maneuver.bearing_after || "";
        const modifier = maneuver.modifier || "";

        // Extract distance and duration
        const distance = step.distance || 0;
        const duration = step.duration || 0;

        // Create a formatted instruction
        const formattedInstruction = {
            instruction: instruction,
            type: typeOfManeuver,
            bearingBefore: bearingBefore,
            bearingAfter: bearingAfter,
            distance: distance,
            duration: duration,
            modifier: modifier
        };
        instructions.push(formattedInstruction);
    });
    // update the display:

    return instructions;
}
export function displayInstruction(instructionTextContent, distanceToCheckpoint, remainingDistance, modifier) {
    // Extract the instruction text from the object    
    // Get the pop-up elements
    console.log("Modifier: " + modifier);
    const instructionPopup = document.getElementById('navigation');
    const instructionIcon = document.getElementById('distanceIcon');
    const instructionText = document.getElementById('instructionText');
    const distanceText = document.getElementById('distanceText');
    if (modifier && modifier.includes('left')) {
        instructionIcon.setAttribute('src', 'static/icons/left.svg');
    } else if (modifier && modifier.includes('right')) {
        instructionIcon.setAttribute('src', 'static/icons/right.svg');
    } else {
        instructionIcon.setAttribute('src', 'static/icons/lines.svg');
    }

    // Convert remaining distance to kilometers
    const remainingDistanceKm = (remainingDistance / 1000).toFixed(2);
    document.querySelector('#journeyDistance h3').textContent = remainingDistanceKm;

    // Convert total duration to minutes
    const remainingDuration = calculateRemainingDuration(remainingDistance, 1.4);
    document.querySelector('#journeyDuration h3').textContent = remainingDuration;
    // Get the current time
    const currentTime = new Date();

    // Calculate the ETA by adding the remaining duration (in minutes) to the current time
    const etaTime = new Date(currentTime.getTime() + remainingDuration * 60 * 1000);

    // Format the ETA to show only the hours and minutes
    const etaHours = etaTime.getHours().toString().padStart(2, '0');
    const etaMinutes = etaTime.getMinutes().toString().padStart(2, '0');
    const formattedETA = `${etaHours}:${etaMinutes}`;
    // Update the ETA in the UI
    document.querySelector('#journeyETA h3').textContent = formattedETA;
    // Update the text content with the extracted instruction
    instructionText.textContent = instructionTextContent;
    distanceText.textContent = `${distanceToCheckpoint.toFixed(1)} metres`;
    // Show the pop-up
    instructionPopup.classList.add('fadeshowin')
}
// Navigation Mode 
export function enableNavigationMode(data) {
    sharedState.instructions = getInstructions(data);
    document.getElementById('popupModal').style.display = "none";
    const geolocate = document.getElementsByClassName('mapboxgl-ctrl-top-right')[0]
    geolocate.style.top = '210px'
    sharedState.isUserRunning = true
    const instructionPopup = document.getElementById('navigation');
    if (sharedState.routeIndex == 0) {
        const firstInstruction = sharedState.instructions[0];
        // Extract the relevant information for the first instruction
        const instructionTextContent = firstInstruction.instruction; // Text instruction
        const distanceToCheckpoint = firstInstruction.distance; // Distance to the next checkpoint
        const remainingDistance = calculateRemainingDistance(sharedState.route.coordinates); // Assuming you have a function to calculate total remaining distance
        const modifier = firstInstruction.modifier; // Modifier for direction icons (left, right, etc.)
        // Display the first instruction
        displayInstruction(instructionTextContent, distanceToCheckpoint, remainingDistance, modifier);
    }
    // Show the pop-up
    instructionPopup.classList.add('fadeshowin');
    poiSwiper.classList.add('fadeshowin');
    listButton.style.display = 'none';
    // pauseAndpaly.style.display = 'block';
    // Animate the sharedState.map to tilt and zoom for 3D perspective
    sharedState.map.easeTo({
        pitch: 60, // Tilts the map to 60 degrees for a 3D perspective
        zoom: 20,  // Adjust the zoom level for better street view navigation
        center: [sharedState.userLocation.lng, sharedState.userLocation.lat], // Center map on user's location
        duration: 600 // Animation duration in milliseconds
    });
    sharedState.switchoverState = 'FOCUS'
    // Wait for easeTo animation to complete, then start tracking
    sharedState.map.once('moveend', () => trackUserLocation(sharedState.route));
}
// Function to check if user is off-route
export function isUserOffRoute(userLocation, route, tolerance = 0.03) {
    const userCoordinates = [userLocation.lng, userLocation.lat];
    // Extract the coordinates from the route object
    const routeCoordinates = route.coordinates;
    // Create a turf lineString from route coordinates
    const routeLine = turf.lineString(routeCoordinates);

    // Create a buffered area around the route with the specified tolerance
    const bufferedRoute = turf.buffer(routeLine, tolerance, { units: 'kilometers' });

    // Create a point from the user's location
    const userPoint = turf.point(userCoordinates);

    // 计算点到线的最小距离
    const distance = turf.pointToLineDistance(userPoint, routeLine, { units: "miles" }) * 1069;
    const nearestPointOnLine = turf.nearestPointOnLine(routeLine, userPoint, { units: "meters" });
    const notStartLine = turf.lineSlice(nearestPointOnLine, turf.point(route.coordinates[route.coordinates.length - 1]), routeLine);
    const walkedLine = turf.lineSlice(turf.point(route.coordinates[0]), nearestPointOnLine, routeLine);
    if (sharedState.map.getSource('walked-route')) {
        sharedState.map.getSource('walked-route').setData(walkedLine);
    }
    if (sharedState.map.getSource('route')) {
        sharedState.map.getSource('route').setData(notStartLine);
    }
    const isInPolygon = turf.booleanPointInPolygon(userPoint, bufferedRoute);
    // console.log(`user distance: ${distance}(m)`, isInPolygon)
    return { distance, isInPolygon, nearestPointOnLine }
}
// Handle route recalculation when user goes off-route
export function recalculateRoute(currentLocation, destination) {
    const directionsRequest = `https://api.mapbox.com/directions/v5/mapbox/walking/${currentLocation.lng},${currentLocation.lat};${destination[0]},${destination[1]}s?geometries=geojson&steps=true&access_token=${mapboxgl.accessToken}`;

    fetch(directionsRequest)
        .then(response => response.json())
        .then(data => {
            const newRoute = data.routes[0].geometry.coordinates;
            // replace and reset all route memory objects
            sharedState.route = data.routes[0].geometry;
            sharedState.steps = data.routes[0].legs[0].steps;
            sharedState.walkStepsNavs = data;
            sharedState.instructions = getInstructions(steps);
            sharedState.routeIndex = 0;
            if (!sharedState.endPlaceProt) return
            // Update the sharedState.map with new route
            if (sharedState.map.getSource('route')) {
                sharedState.map.getSource('route').setData({
                    'type': 'Feature',
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': newRoute
                    }
                });
            }
            // restart tracking:
            trackUserLocation(sharedState.route);
            if (!sharedState.isUserRunning) {
                paintLine(sharedState.route, false)
            } else {
                setDottedLine()
            }
            console.log("New route calculated and updated on the map.");
        })
        .catch(error => console.error('Error in recalculating route:', error));
}
export function disableNavigationMode() {
    sharedState.map.easeTo({
        pitch: 0, // Back to 2D top-down view
        bearing: 0,
        zoom: 15, // Adjust zoom level if needed
        duration: 1000
    });
    if (simulationRunning) {
        pauseSimulation();
    }
}
export function calculateRemainingDistance(routeCoordinates) {
    let totalRemainingDistance = 0;

    // Iterate over the remaining route coordinates and sum up the distances
    for (let i = 0; i < routeCoordinates.length - 1; i++) {
        // Each point should be an object with 'lat' and 'lng' properties
        const point1 = { lat: routeCoordinates[i][1], lng: routeCoordinates[i][0] };
        const point2 = { lat: routeCoordinates[i + 1][1], lng: routeCoordinates[i + 1][0] };
        const distance = calculateDistance(point1, point2);
        totalRemainingDistance += distance;
    }

    return totalRemainingDistance;
}
export function stopNavFunc() {
    sharedState.endPlaceProt = null
    sharedState.map.setZoom(14);
    sharedState.switchoverState = 'POSINIT'
    closedNavfun();
    poiSwiper.classList.remove('fadeshowin');
    listButton.style.display = 'block';
    pauseAndpaly.style.display = 'none';
    disableNavigationMode();
    simulationRunning = false;
    simulationPaused = false;
    initProperty()
}
export function exitNavFunc() {
    sharedState.endPlaceProt = null
    closedNavfun();
    poiSwiper.classList.remove('fadeshowin');
    listButton.style.display = 'block';
    navcompleted.classList.remove('fadeshowin');
    navcompleted.classList.add('fadeout');
    disableNavigationMode();
}
export async function navFunc(e, typeSuge, place, longAndlat, fromUser) {
    const popupModal = document.getElementById('popupModal');
    popupModal.style.display = 'none';
    console.log('-------->>>>>>', simulationRunning, simulationPaused)
    if (simulationRunning || simulationPaused) return;
    disminiNav();
    let places = []
    let waypoints = []
    let isfromUser = fromUser && fromUser === '1' ? false : true
    if (place && longAndlat) {
        places = [place]
        waypoints = [longAndlat.split(',')]
    }
    if (typeSuge && typeSuge === 'suggestion' && suggestionData) {
        waypoints = suggestionData.coordinates.map(coord => [coord.lng, coord.lat]);
        places = suggestionData.places;
    }
    if (waypoints.length && places.length) {
        await displayRoute(places, waypoints, isfromUser);
    }
    paintLine(sharedState.route)
}
export function closedNavfun() {
    const navigationElem = document.getElementById('navigation');
    navigationElem.classList.remove('fadeshowin');
    navigationElem.classList.add('fadeout');
    if (sharedState.map.getLayer('route')) {
        sharedState.map.removeLayer('route');
    }
    if (sharedState.map.getSource('route')) {
        sharedState.map.removeSource('route');
    }
    if (sharedState.map.getLayer('walked-route')) {
        sharedState.map.removeLayer('walked-route');
    }
    if (sharedState.map.getSource('walked-route')) {
        sharedState.map.removeSource('walked-route');
    }
    if (sharedState.map.getLayer('prewroute')) {
        sharedState.map.removeLayer('prewroute');
    }
    if (sharedState.map.getLayer('lineBorder')) {
        sharedState.map.removeLayer('lineBorder');
    }
    if (sharedState.map.getLayer('dottedLineroute')) {
        sharedState.map.removeLayer('dottedLineroute');
    }
    const geolocate = document.getElementsByClassName('mapboxgl-ctrl-top-right')[0]
    geolocate.style.top = '80px'
    sharedState.isUserRunning = false
    sharedState.endPlaceProt = null
}
export function setMapRoute(resRoute) {
    if (!sharedState.map.getLayer('route')) {
        sharedState.map.loadImage(
            'static/icons/nav.png',
            (error, image) => {
                if (error) throw error;
                if (!sharedState.map.hasImage('arrow')) {
                    sharedState.map.addImage('arrow', image);
                }
                // Add route to map
                if (!sharedState.map.getSource('route')) {
                    sharedState.map.addSource('route', {
                        'type': 'geojson',
                        'data': {
                            'type': 'Feature',
                            'properties': {},
                            'geometry': resRoute
                        }
                    });
                }
                sharedState.map.addLayer({
                    id: 'route',
                    type: 'line',
                    source: 'route',
                    layout: {
                        'icon-size': 0.8,
                        'icon-allow-overlap': false,
                        'line-cap': 'round'
                    },
                    paint: {
                        'line-pattern': 'arrow',
                        'line-width': 10
                    }
                });
            }
        );

        // Update route data on map
        sharedState.directions.on('route', function (e) {
            const route = e.route[0].geometry;
            sharedState.map.getSource('route').setData(route);
        });
    }

    if (!sharedState.map.getSource('walked-route')) {
        sharedState.map.addSource('walked-route', {
            "type": "geojson",
            "data": {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": []
                }
            }
        });
    }

    if (!sharedState.map.getLayer('walked-route')) {
        // sharedState.map.addLayer({
        //     "id": "walked-route",
        //     "type": "symbol",
        //     "source": "walked-route",
        //     'layout': {
        //         'symbol-placement': 'line',
        //         'symbol-spacing': 2,
        //         'icon-image': 'walkedArrow',
        //         'icon-size': 0.5,
        //         'icon-allow-overlap': true,
        //     },
        // });
        sharedState.map.addLayer({
            id: 'walked-route',
            type: 'line',
            source: 'walked-route',
            layout: {
                'icon-size': 0.8,
                'icon-allow-overlap': false,
                'line-cap': 'round'
            },
            paint: {
                'line-pattern': 'walkedArrow',
                'line-width': 10
            }
        });
    }
}
export function startUserNav() {
    sharedState.firstClick = true
    sharedState.userTouch = false
    console.log('-----steps-->>>', sharedState.steps)
    const img = dingwenndId.getElementsByTagName('img')[0]
    img.setAttribute('src', `static/icons/nios.svg`);
    if (sharedState.map.getLayer('prewroute')) {
        sharedState.map.removeLayer('prewroute');
    }
    if (sharedState.map.getLayer('lineBorder')) {
        sharedState.map.removeLayer('lineBorder');
    }
    setDottedLine()
    setMapRoute(sharedState.route)
    startNav.classList.remove('fadeshowin');
    enableNavigationMode(sharedState.steps);
}
export function cancelNav() {
    sharedState.endPlaceProt = null
    closedNavfun();
    sharedState.map.easeTo({
        pitch: 0, // Back to 2D top-down view
        bearing: 0,
        zoom: 15, // Adjust zoom level if needed
        duration: 1000
    });
    listButton.style.display = 'block';
    startNav.classList.remove('fadeshowin');
}