// Fetch the access token from the Flask endpoint and initialize the map
var waypoints = [];
var map;
var directions;
var walkedRoute = [];
let route = {};
let api_response = {};
let navigationEnabled = false;
let simulationRunning = false; // Flag to indicate if the simulation is running
let simulationPaused = false;  // Flag to indicate if the simulation is paused
let simulationTimeout;         // Variable to store the timeout ID
let userMarker;
let userLocation;
let isFirstOpen = false;
let startMarker;
let nedMarker;
let steps;
let routeIndex = 0;
let increment = true;
let currentStepIndex = 0; // Start at the first step of the route


// User location
function getUserCurrentPosition(callBack, error) {
    navigator.geolocation.getCurrentPosition((position) => {
        userLocation = {
            lng: position.coords.longitude,
            lat: position.coords.latitude
        };
        if (callBack) {
            callBack(userLocation)
        }
        // get POIs
        getPoisByLocation(userLocation)
        console.log(`User location updated to: ${userLocation.lat}, ${userLocation.lng}`);
    }, (e) => {
        if (error) {
            cuerror(e)
        }
        console.error('Error obtaining geolocation:', e);
    });
}

async function getPoisByLocation(location) {
    try {
        const response = await fetch('/find_nearby_pois', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ user_location: { longitude: location.lng, latitude: location.lat }, radius_in_meters: 500 })
        });

        if (!response.ok) {
            throw new Error('Network response was not ok');
        }

        const poisData = await response.json();
        const placeInfoResponse = await fetchPlacesData(poisData)
        const swiperconent = document.getElementById('swiperconent')
        const poiList = document.getElementById('poiList')
        let contenxt = '';
        let listCont = '';
        poisData.forEach((placeName, index) => {
            const base64Thumbnail = placeInfoResponse[placeName] ? `data:image/jpeg;base64,${placeInfoResponse[placeName].thumbnail}` : '/static/icons/default.png';
            contenxt += `<div class="swiper-slide" key='${index}' data-name='${placeName}'>
                            <div class="slideItme">
                                <div class="swperimg">
                                    <img src="${base64Thumbnail}" alt="${placeName}" srcset="">
                                </div>
                                <div class="visitors">
                                    <h4>${placeName}</h4>
                                    <p class="vistDesc"><span class="islander">Islander earns 50 points</span></p>
                                    <p class="address">
                                        <span>
                                            <img src="static/icons/addess.svg" alt="" srcset="">
                                            500m
                                        </span>
                                        <span>
                                            <img src="static/icons/time.svg" alt="" srcset="">
                                            5mins
                                        </span>
                                    </p>
                                </div>
                            </div>
                        </div>`;
            listCont += `<div class="itemSlide" key='${index}' data-name='${placeName}'>
                            <div class="listimg">
                                <img src="${base64Thumbnail}" alt="${placeName}" width="100%" srcset="">
                            </div>
                            <div class="titleBox">
                                <div class="title">${placeName}</div>
                                <div class="rightimg">
                                    <button onclick="navDitle(event, '${placeName}')">
                                        <img src="static/icons/navimg.svg" alt="" srcset="">
                                    </button>
                                    <span>Wait 5 mins</span>
                                </div>
                            </div>
                            <div class="disqu vistDesc">
                                <span class="islander">Islander earns 50 points</span>
                            </div>
                        </div>
                        `;
        });
        swiperconent.innerHTML = contenxt
        poiList.innerHTML = listCont
    } catch (error) {
        console.error('Get Pois by Location', error);
        return null;
    }
}

const mapEl = document.getElementById('map')
const poiList = document.getElementById('poiList')
const tabMap = document.getElementById('tabMap')
const tabList = document.getElementById('tabList')
const poiSwiper = document.getElementById('poiSwiper');
const zoomControls = document.getElementById('zoom-controls');
const pauseAndpaly = document.getElementById('pauseAndpaly');
const listButton = document.getElementsByClassName('mapandlistbut')[0]

window.onload = function () {
    const tishiDom = document.getElementById('tishi')
    isFirstOpen = localStorage.getItem('isFirstOpen')
    const popupModal = document.getElementById('popupModal');
    const btn = document.getElementById("robotIcoId");
    const stopNav = document.getElementById('closedBut')

    stopNav.onclick = function () {
        closedNavfun();
        poiSwiper.classList.remove('fadeshowin');
        listButton.style.display = 'block';
        pauseAndpaly.style.display = 'none';
        disableNavigationMode();
    }

    pauseAndpaly.onclick = function () {
        const imgs = pauseAndpaly.getElementsByTagName('img')[0]
        imgs.setAttribute('src', `static/icons/${simulationRunning ? 'continue' : 'pause'}.svg`);
        if (simulationRunning) {
            pauseSimulation();
        } else {
            simulateUserLocation(route);
        }
    }

    btn.onclick = function () {
        popupModal.style.display = "block";
        tishiDom.style.display = "none";
        localStorage.setItem('isFirstOpen', true)
    }
    window.onclick = function (event) {
        if (event.target === popupModal) {
            popupModal.style.display = "none";
        }
    }

    if (tishiDom && isFirstOpen) {
        tishiDom.style.display = 'none'
    } else {
        tishiDom.style.display = 'block'
    }
    getUserCurrentPosition();
    const swiper = new Swiper('.swiper', {
        loop: true,
        // autoplay: true,
        // delay: 50000,
        slidesPerView: "auto",
        spaceBetween: 16,
        pagination: {
            el: '.swiper-pagination',
        },
    });
    swiper.on('click', function (swiper, event) {
        const swiperconent = document.getElementById('swiperconent');
        const place = swiperconent.querySelector(`div[key='${swiper.activeIndex}']`).getAttribute('data-name');
        getPlaceCoordWithName(place);
    });
}

async function getPlaceCoordWithName(place) {
    disableNavigationMode();
    closedNavfun();
    if (map.getSource('route')) {
        map.removeLayer('route');
        map.removeSource('route');
        if (map.getLayer('directions')) {
            map.removeLayer('directions');
        }
    }
    let response = await fetch('/get_coordinates', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            places: [place],
        })
    });

    if (!response.ok) {
        throw new Error('Network response was not ok ' + response.statusText);
    }

    let responseData = await response.json();
    let waypoints = responseData.coordinates.map(coord => [coord.lng, coord.lat]);
    map.flyTo({
        center: waypoints[0],
        essential: true
    });
    addMarkers([place], waypoints);
}

function systemQuestionFunc(e) {
    const chatMessages = document.getElementById("chatbot-messages");
    postMessage(e.target.innerText, chatMessages);
}

function navDitle(e, name) {
    getPlaceCoordWithName(name);
    mapEl.style.display = 'block';
    poiList.style.display = 'none';
    tabList.classList.remove('activeButton');
    tabMap.classList.add('activeButton');
}

function handerMap(e, type) {
    if (type === 'list') {
        tabMap.classList.remove('activeButton');
        mapEl.style.display = 'none'
        poiList.style.display = 'block'
    } else {
        tabList.classList.remove('activeButton');
        mapEl.style.display = 'block'
        poiList.style.display = 'none'
    }
    e.preventDefault();
    e.target.classList.add('activeButton')
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
            zoom: 13
        });

        directions = new MapboxDirections({
            accessToken: mapboxgl.accessToken,
            unit: 'metric',
            profile: 'mapbox/walking'
        });
        // variable to allow resizing function
        window.mapboxMap = map;
        map.on('load', function () {
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
            // Initial setup for route layers
            map.addSource('walked-route', {
                "type": "geojson",
                "data": {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": []
                    }
                }
            });

            map.loadImage('static/icons/walked.png', function (err, image) {
                if (err) {
                    console.error('Error loading image:', err);
                    reject(err);
                }
                map.addImage('walkedArrow', image);
            });

            map.addLayer({
                "id": "walked-route",
                "type": "symbol",
                "source": "walked-route",
                'layout': {
                    'symbol-placement': 'line',
                    'symbol-spacing': 2,
                    'icon-image': 'walkedArrow',
                    'icon-size': 0.7,
                    'icon-allow-overlap': true,
                },
            });


            // user location control
            // Add the Geolocate Control to the map
            map.addControl(geolocateControl);

            // Override the geolocate event to use navigator.geolocation
            geolocateControl.on('geolocate', () => {
                getUserCurrentPosition((userLoc) => {
                    // Set the user's location on the map
                    map.flyTo({
                        center: [userLoc.lng, userLoc.lat],
                        essential: true // this animation is considered essential with respect to prefers-reduced-motion
                    });
                });
            });
        });
    })
    .catch(error => {
        console.error('Error fetching the access token:', error);
    });

// Navigation Mode 
function enableNavigationMode(data) {
    instructions = getInstructions(data);
    document.getElementById('popupModal').style.display = "none";
    const instructionPopup = document.getElementById('navigation');
    // Show the pop-up
    instructionPopup.classList.add('fadeshowin');
    poiSwiper.classList.add('fadeshowin');
    listButton.style.display = 'none';
    pauseAndpaly.style.display = 'block';

    // Animate the map to tilt and zoom for 3D perspective
    map.easeTo({
        pitch: 60, // Tilts the map to 60 degrees for a 3D perspective
        zoom: 20,  // Adjust the zoom level for better street view navigation
        center: [userLocation.lng, userLocation.lat], // Center map on user's location
        duration: 500 // Animation duration in milliseconds
    });

    // Wait for easeTo animation to complete, then start simulation
    map.once('moveend', simulateUserLocation(route));
    // Monitor the user's GPS location
    //navigator.geolocation.watchPosition((position) => {
    // navigator.geolocation.getCurrentPosition((position) => {
    //     // disable tracking of location for simulation.
    //     // const userLocation = {
    //     //     lng: position.coords.longitude,
    //     //     lat: position.coords.latitude
    //     // };
    //     // const userHeading = position.coords.heading || 0;

    //     // // Rotate the map to match the user's heading
    //     // map.rotateTo(userHeading);

       

    // }, (error) => {
    //     console.error('Error getting user location:', error);
    // });
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
    if (simulationRunning) {
        pauseSimulation();
    }
}
function calculateRemainingDistance(routeCoordinates) {
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

function displayInstruction(instructionTextContent, distanceToCheckpoint, remainingDistance, modifier) {
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

    // Calculate the ETA by adding the remaining duration (in seconds) to the current time
    const etaTime = new Date(currentTime.getTime() + remainingDuration * 1000);

    // Format the ETA to show only the hours and minutes
    const etaHours = etaTime.getHours().toString().padStart(2, '0');
    const etaMinutes = etaTime.getMinutes().toString().padStart(2, '0');
    const formattedETA = `${etaHours}:${etaMinutes}`;
    // Update the ETA in the UI
    document.querySelector('#journeyETA h3').textContent = formattedETA;
    // Update the text content with the extracted instruction
    instructionText.textContent = instructionTextContent;
    distanceText.textContent = `${distanceToCheckpoint.toFixed(1)}`;
    // Show the pop-up
    instructionPopup.classList.add('fadeshowin')
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

// Function to update navigation instructions based on user's current location
let previousDistanceToCheckpoint = Infinity; // Initialize with a large number
function updateNavigationInstructions(userLocation, nextPosition) {
    const thresholdDistance = 5;
    // Calculate the distance between the user's current location and the next checkpoint
    const checkpoint = {
        lng: steps[currentStepIndex].maneuver.location[0],
        lat: steps[currentStepIndex].maneuver.location[1]
    };
    const distanceToCheckpoint = calculateDistance(userLocation, checkpoint);
    console.log("Currently tracking checkpoint: " + JSON.stringify(checkpoint));

    // Calculate the bearing using the next interpolated position instead of the checkpoint
    const userHeading = calculateBearing(userLocation.lat, userLocation.lng, nextPosition.lat, nextPosition.lng);
    
    map.easeTo({
        pitch: 60, // Tilts the map to 60 degrees for a 3D perspective
        zoom: 20,  // Adjust the zoom level for better street view navigation
        center: [userLocation.lng, userLocation.lat], // Center map on user's location
        duration: 500, // Animation duration in milliseconds
        bearing: userHeading 
    });

    let increment = false;

    // Check if the user is at the start of the navigation and ahead of the first checkpoint
    if (currentStepIndex === 0 && distanceToCheckpoint > previousDistanceToCheckpoint) {
        // Skip to the next checkpoint if the user is ahead of the first one
        currentStepIndex++;
        console.log("User started ahead of the first checkpoint, skipping to step index: " + currentStepIndex);
        increment = true;
    } else if (distanceToCheckpoint < thresholdDistance) {
        // If the user is close enough to the checkpoint, move to the next step
        currentStepIndex++;
        console.log("Threshold met, incrementing step index to: " + currentStepIndex);
        increment = true;
    }

    previousDistanceToCheckpoint = distanceToCheckpoint; // Update the previous distance

    // Load the next instruction if the step index was incremented
    if (currentStepIndex < instructions.length && increment) {
        const nextInstructionObject = instructions[currentStepIndex].instruction;
        const remainingDist = calculateRemainingDistance(route.coordinates.slice(routeIndex));
        console.log("Remaining distance to destination: " + remainingDist);
        const modifierType = instructions[currentStepIndex].modifier;
        displayInstruction(nextInstructionObject, distanceToCheckpoint, remainingDist, modifierType);
        increment = false;
    } else {
        const remainingDist = calculateRemainingDistance(route.coordinates.slice(routeIndex));
        document.getElementById("distanceText").textContent = `${distanceToCheckpoint.toFixed(1)}`;
            // Update remaining distance in kilometers
        const remainingDistanceKm = (remainingDist / 1000).toFixed(2);
        document.querySelector('#journeyDistance h3').textContent = remainingDistanceKm;
        
        // Calculate and update the remaining duration
        const remainingDuration = calculateRemainingDuration(remainingDist, 1.4);
        document.querySelector('#journeyDuration h3').textContent = remainingDuration;

    }
}

//May need to implement different modes : change walking speed.
function calculateRemainingDuration(remainingDistance, walkingSpeed) {
    // Calculate the remaining duration in seconds
    const remainingDuration = (remainingDistance / walkingSpeed / 60).toFixed(0);

    return remainingDuration;
}
// calculate user bearing;
function calculateBearing(lat1, lng1, lat2, lng2) {
    const degToRad = Math.PI / 180.0;
    const φ1 = lat1 * degToRad;
    const φ2 = lat2 * degToRad;
    const λ1 = lng1 * degToRad;
    const λ2 = lng2 * degToRad;

    const θ = Math.atan2(
      Math.sin(λ2 - λ1) * Math.cos(φ2),
      Math.cos(φ1) * Math.sin(φ2) -
        Math.sin(φ1) * Math.cos(φ2) * Math.cos(λ2 - λ1),
    );

    return ((θ * 180) / Math.PI + 360) % 360;
}
// Function to start simulating user location along the route with smooth movement
// Function to start simulating user location along the route with smooth movement
function simulateUserLocation(route) {
    console.log("Starting simulation");
    const targetDistance = 5; // meters per step for interpolation

    // Initialize the user marker if it doesn't exist
    if (!userMarker) {
        const el = document.createElement('div');
        el.insertAdjacentHTML('beforeend', `<p><img src="static/icons/cuser.svg" alt="" srcset=""></p>`);
        userMarker = new mapboxgl.Marker({
            color: 'red',
            // rotation: 45,
            element: el
        })
            .setLngLat([route.coordinates[0][0], route.coordinates[0][1]])
            .addTo(map);
    }

    function updateLocation() {
        if (!simulationRunning) return; // If not running, do nothing

        if (routeIndex < route.coordinates.length - 1) {
            // Simulate the user's location along the route
            const currentPosition = {
                lng: route.coordinates[routeIndex][0],
                lat: route.coordinates[routeIndex][1]
            };
            const nextPosition = {
                lng: route.coordinates[routeIndex + 1][0],
                lat: route.coordinates[routeIndex + 1][1]
            };
            getPoisByLocation(currentPosition);
            // Calculate the distance between the current and next position
            const distance = distanceBetweenPoints([currentPosition.lng, currentPosition.lat], [nextPosition.lng, nextPosition.lat]);

            // Animate the marker along the path between current and next position
            function animateMarker(interpolatedPosition) {
                if (!simulationRunning) return; // If not running, do nothing

                // Update the user's location in your app
                updateUserLocation({ lng: interpolatedPosition[0], lat: interpolatedPosition[1] });

                // Update marker position
                userMarker.setLngLat(interpolatedPosition);

                // Calculate remaining distance to next position
                const remainingDistance = distanceBetweenPoints(interpolatedPosition, [nextPosition.lng, nextPosition.lat]);
                updateWalkedRoute(currentPosition);
                updateRemainingRoute(currentPosition);
                // If the remaining distance is less than the target, move to the next point
                if (remainingDistance <= targetDistance) {
                    routeIndex++;

                    if (routeIndex < route.coordinates.length - 1) {
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
                    setTimeout(() => animateMarker(newInterpolatedPosition), 1200);
                }

                // Update navigation instructions based on the user's location and the next interpolated position
                console.log("User location: " + JSON.stringify(userLocation));
                updateNavigationInstructions({ lng: interpolatedPosition[0], lat: interpolatedPosition[1] }, nextPosition);
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


function updateWalkedRoute(currentPosition) {
    // Add the current position to the walked route
    walkedRoute.push([currentPosition.lng, currentPosition.lat]);

    // Update the map with the walked route
    map.getSource('walked-route').setData({
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": walkedRoute
        }
    });
}

function updateRemainingRoute(currentPosition) {
    // Update the remaining route after trimming
    const remainingRoute = route.coordinates.slice(routeIndex);
    remainingRoute.unshift([currentPosition.lng, currentPosition.lat]);
    map.getSource('route').setData({
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": remainingRoute
        }
    });
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
    userLocation = location;
    console.log("User location updated:", location);
}


// Function to pause the simulation
function pauseSimulation() {
    console.log(route)
    if (simulationRunning && !simulationPaused) {
        simulationPaused = true;
        simulationRunning = false;
        clearTimeout(simulationTimeout); // Stop the current timeout
        console.log("Simulation paused");
    }
}

// Function to stop the simulation
function stopSimulation() {
    simulationRunning = false;
    simulationPaused = false;
    rouetIndex = 0;
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

function displayRoute(placeNames, rawCoordinates, fromUser) {
    return new Promise((resolve, reject) => {
        // Clear existing routes
        if (map.getSource('route')) {
            map.removeLayer('route');
            map.removeSource('route');
            if (map.getLayer('directions')) {
                map.removeLayer('directions');
            }
        }
        addMarkers(placeNames, rawCoordinates);

        // Check number of waypoints. If less than 25, execute the usual. Else, fetch centroids.
        let fetchDirectionsPromise;
        let allCoordinates;
        if (fromUser) {
            allCoordinates = [[userLocation.lng, userLocation.lat], ...rawCoordinates];
        } else {
            allCoordinates = rawCoordinates;
        }
        console.log("Coordinates to go to: " + allCoordinates)
        const coordinates = allCoordinates.map(coord => coord.join(',')).join(';');
        var url = `https://api.mapbox.com/directions/v5/mapbox/walking/${coordinates}?geometries=geojson&steps=true&access_token=${mapboxgl.accessToken}`;
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
                    api_response = data.routes[0]
                    route = data.routes[0].geometry;
                    steps = data.routes[0].legs[0].steps;
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
                        if (!map.hasImage('arrow')) {
                            const url = 'static/icons/nav.png';
                            map.loadImage(url, function (err, image) {
                                if (err) {
                                    console.error('Error loading image:', err);
                                    reject(err);
                                }
                                map.addImage('arrow', image);
                            });
                        }
                        // Add arrow-line layer
                        map.addLayer({
                            'id': 'route',
                            'type': 'symbol',
                            'source': 'route',
                            'layout': {
                                'symbol-placement': 'line',
                                'symbol-spacing': 2,
                                'icon-image': 'arrow',
                                'icon-size': 0.7,
                                'icon-allow-overlap': true,
                            },
                        });

                        // Update route data on map
                        directions.on('route', function (e) {
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
async function getOptimizedSequence(placeNames, chatMessages) {
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
            appendMessage('It seems my network connection with you is unstable. Please try sending me your message again.', 'guide-message', chatMessages, 'message');
            throw new Error('Network response was not ok');
        }

        const coordSequence = await response.json();

        // Check if the response contains a message key, indicating an error
        if (coordSequence.message) {
            appendMessage(coordSequence.message, 'guide-message', chatMessages, 'message');
            return;
        }

        return coordSequence;
    } catch (error) {
        console.error('Error optimizing coordinates:', error);

        // Display a generic error message using appendMessage
        return;
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
        if (data.operation == "route" && data.response.length > 1) {
            console.log("PLaces: " + data.response);
            let cleanedPlaceNames = data.response;

            console.log(cleanedPlaceNames); // Check the cleaned list
            // Get the route from the get_coordinates function
            let orderOfVisit = await get_coordinates(cleanedPlaceNames, false);
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
            appendMessage(textData.response, "guide-message", chatMessages, 'route');
            //appendMessage(instr, "nav-button", chatMessages);
            attachEventListeners();
        } else if (data.operation == "location") {
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
            appendMessage(textData.response, "guide-message", chatMessages, 'location');
            attachEventListeners();
        } else if (data.operation == "wayfinding") {
            console.log("PLaces: " + data.response);
            let cleanedPlaceNames = data.response;

            console.log(cleanedPlaceNames); // Check the cleaned list
            // Get the route from the get_coordinates function
            let orderOfVisit = await get_coordinates(cleanedPlaceNames, true);
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
            appendMessage(textData.response, "guide-message", chatMessages, 'route');
            //appendMessage(instr, "nav-button", chatMessages);
            attachEventListeners();
        } else { // return message directly
            appendMessage(data.response, 'guide-message', chatMessages);
        }
    } catch (error) {
        console.error('Error:', JSON.stringify(error));
    } 
}

function navFunc(e, id) {
    const popupModal = document.getElementById('popupModal');
    const navigation = document.getElementById('navigation');
    navigation.classList.add('fadeshowin')
    popupModal.style.display = 'none';
    return
    const lineData = {
        type: 'Feature',
        geometry: {
            type: 'LineString',
            coordinates: [
                [103.826511, 1.248450],
                [103.827457, 1.248179],
                [103.827967, 1.247061],
                [103.829030, 1.246154],
                [103.829098, 1.245841],
                [103.828930, 1.245373],
                [103.828544, 1.244633],
                [103.827659, 1.245229],
            ]
        },
        properties: {}
    };
    map.addSource('route', {
        type: 'geojson',
        data: lineData
    });
    map.loadImage(
        'static/icons/nav.png',
        (err, image) => {
            console.log(image)
            if (err) throw err;
            map.addImage('pattern', image);
            map.addLayer({
                'id': 'route',
                'type': 'symbol',
                'source': 'route',
                'layout': {
                    'symbol-placement': 'line',
                    'symbol-spacing': 2,
                    'icon-image': 'pattern',
                    'icon-size': 0.5,
                    'icon-allow-overlap': true,
                },
            });
            map.setPitch(45);
            // 实时跟踪用户位置
            if (navigator.geolocation) {
                navigator.geolocation.watchPosition(position => {
                    const userLocation = lineData.geometry.coordinates[0]
                    console.error("asdsdsd", userLocation);
                    // const userLocation = [position.coords.longitude, position.coords.latitude];
                    map.setCenter(userLocation);
                    map.rotateTo(90, { duration: 0 })
                    map.flyTo({
                        center: lineData.geometry.coordinates[0],
                        zoom: 20, // 可设置缩放级别
                        speed: 1.5 // 飞行速度
                    });
                }, error => {
                    console.error("无法获取当前位置：", error);
                }, {
                    enableHighAccuracy: true,
                    maximumAge: 0,
                    timeout: 5000
                });
            }
            startMarker = new mapboxgl.Marker({
                draggable: true,
                color: '#83f7a0'
            })
                .setLngLat(lineData.geometry.coordinates[0])
                .addTo(map);
            // if (window.DeviceOrientationEvent) {
            //     window.addEventListener('deviceorientation', (event) => {
            //         if (event.alpha !== null) {
            //             const heading = 360 - event.alpha; // 获取设备的方向
            //             // 实时旋转地图
            //             map.rotateTo(heading, {
            //                 duration: 0 // 禁用动画，使旋转更顺畅
            //             });
            //         }
            //     });
            // } else {
            //     console.error("浏览器不支持设备方向事件");
            // }
            nedMarker = new mapboxgl.Marker({
                draggable: true,
                color: '#ed6461'
            })
                .setLngLat(lineData.geometry.coordinates[lineData.geometry.coordinates.length - 1])
                .addTo(map);
        }
    );
}

function closedNavfun() {
    const navigation = document.getElementById('navigation');
    navigation.classList.remove('fadeshowin');
    navigation.classList.add('fadeout');
    if (map.getLayer('route')) {
        map.removeLayer('route');
    }
    if (map.getSource('route')) {
        map.removeSource('route');
    }
    // if (map.hasImage('pattern')) {
    //     map.removeImage('pattern');
    // }
    // startMarker.remove();
    // nedMarker.remove();
}

// creaate template and styles for each visitor/guide message.
function appendMessage(text, className, chatMessages, type) {
    if (className == "guide-message") {
        if (type === 'route') {
            chatMessages.innerHTML += `<div class='chat-message ${className}'>
            <div class='guideImage'><img src="static/icons/choml.png" alt="" srcset=""></div>
            <div class='guideText'>
                <div class='messageStype'>
                    ${text}
                    <p style='margin-top: 10px;'>
                        <button id="detailsButton">
                            Details
                        </button>
                        <button id="takeThereBut" onclick="navFunc(event, '${className}')">
                            <img src="static/icons/daohang.svg" alt="" srcset="">
                            <span>Take me there</span>
                        </button>
                    </p>
                </div>
            </div>
        </div>
        `
        } else {
            chatMessages.innerHTML += `<div class='chat-message ${className}'>
            <div class='guideImage'><img src="static/icons/choml.png" alt="" srcset=""></div>
            <div class='guideText'>
                <div class='messageStype'>
                    ${text}
                </div>
            </div>
        </div>
        `
        }
    } else {
        chatMessages.innerHTML += `<div class='chat-message ${className}'>${marked.parse(text)}</div>`
    }
    var takeThereBut = document.getElementById("takeThereBut");
    if (takeThereBut) {
        takeThereBut.addEventListener("click", function () {
            // Call your function here
            enableNavigationMode(steps);
        });
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
        button.addEventListener('click', function () {
            if (!navigationEnabled) {
                enableNavigationMode(text);
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

function getInstructions(data) {
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
    console.log("instructions length: " + instructions.length);
    console.log("Full instr: " + JSON.stringify(instructions));
    return instructions;
}

async function get_coordinates(data, fromUser) {
    let placeNames = data;
    if (fromUser) {    
        try {
            // Fetch the user's current location
            userLocation = await new Promise((resolve, reject) => {
                getUserCurrentPosition((userLoc) => resolve(userLoc), () => reject(error));
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

            let instr = await displayRoute(orderOfVisit[0], orderOfVisit[1], true);
            return [orderOfVisit, instr];
        } catch (error) {
            console.error('Error fetching coordinates:', error);
        }
    } else {
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

            let instr = await displayRoute(orderOfVisit[0], orderOfVisit[1], false);
            return [orderOfVisit, instr];
        } catch (error) {
            console.error('Error fetching coordinates:', error);
        }
    };
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
        placeNames = responseData.places && responseData.places.length ? responseData.places : data;

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
                placeName = placeName.replace(/[\[\]]/g, '');
                console.log(placeName)

                var place = {
                    description: placesData[placeName] ? placesData[placeName]['description'] : '',
                    name: placeName,
                };
                // Use the Base64 thumbnail fetched from the backend
                var base64Thumbnail = placesData[placeName] ? placesData[placeName].thumbnail : '';  // Update: Access the thumbnail from the nested object
                if (base64Thumbnail) {
                    place.thumbnail = `data:image/jpeg;base64,${base64Thumbnail}`;
                } else {
                    place.thumbnail = '/static/icons/default.png'; // Fallback if no thumbnail is found
                }

                var popupContentString = populateTemplate(template, place);
                var doc = parser.parseFromString(popupContentString, 'text/html');
                var popupContent = doc.querySelector('.info-card-content');
                popupContent.querySelector('button').onclick = async function () {
                    await displayRoute([name], [coord], true);
                    enableNavigationMode(steps);
                }
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
// document.getElementById('zoom-in').addEventListener('click', () => {
//     map.zoomIn();
// });

// document.getElementById('zoom-out').addEventListener('click', () => {
//     map.zoomOut();
// });

// Add event listeners to the hyperlinks
function attachEventListeners() {
    document.querySelectorAll('.location-link').forEach(function (link) {
        link.addEventListener('click', function (e) {
            const markerId = this.getAttribute('data-marker-id');
            // Hide the popup modal
            document.getElementById('popupModal').style.display = 'none';
            Object.keys(window.mapMarkers).forEach(item => {
                if (window.mapMarkers[item].getPopup().isOpen()) {
                    window.mapMarkers[item].togglePopup()
                }
            })
            const marker = window.mapMarkers[markerId]; // Get the marker
            if (marker) { // Ensure marker exists
                var markerCoordinates = marker.getLngLat();
                
                // Center the map on the marker's coordinates
                window.map.flyTo({
                    center: markerCoordinates,
                    zoom: 15, // Adjust the zoom level as needed
                    essential: true // This ensures the animation is considered essential by the browser
                });

                // Show the map popup if it's not already open
                if (!marker.getPopup().isOpen()) {
                    marker.togglePopup(); // Open the popup if it's not already open
                }
            } else {
                if (e.target.innerText) {
                    getPlaceCoordWithName(e.target.innerText);
                }
                console.error('Marker with ID ' + markerId + ' not found.');
            }
        });
    });
}
