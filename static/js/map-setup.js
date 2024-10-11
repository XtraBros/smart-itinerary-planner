// Fetch the access token from the Flask endpoint and initialize the map
var waypoints = [];
var map;
var directions;
var geolocateControl;
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
let suggestionData;
let thumbnailURI;
let endPlaceProt; // end port
let simulatePoint;
let isUserRunning = false;
let walkStepsNavs;
let suggestionTimer = null;  // To store the timer instance
const suggestionTimeout = 5 * 60 * 1000;  // 5 minutes in milliseconds

function initProperty() {
    routeIndex = 0;
    currentStepIndex = 0;
    walkedRoute = []
    simulatePoint = null
    clearTimeout(simulationTimeout);
}

// User location
function getUserCurrentPosition(callBack, error) {
    navigator.geolocation.getCurrentPosition((position) => {
        userLocation = {
            lng: position.coords.longitude,
            lat: position.coords.latitude,
            userHeading: position.coords.heading,
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
        const placeInfoResponse = await fetchPlacesData(poisData);
        if (poisData && !poisData.length) return
        const swiperconent = document.getElementById('swiperconent');
        const poiList = document.getElementById('poiList');
        const orderOfVisit = await get_coordinates_without_route(poisData);

        fetchTemplate('static/html/info-card.html').then(template => {
            const parser = new DOMParser();
            let contenxt = '';
            let listCont = '';
            poisData.forEach((placeName, index) => {
                // Construct the Google Cloud thumbnail URL
                var formattedPlaceName = placeName.toLowerCase().replace(/\s+/g, '-');
                // Check if placeName contains "station" or "toilet" and update accordingly
                if (placeName.toLowerCase().includes("tiolet")) {
                    formattedPlaceName = "toilet";
                } else if (placeName.toLowerCase().includes("station")) {
                    formattedPlaceName = "station";
                }
                const thumbnailUrl = placeInfoResponse[placeName] ? `${thumbnailURI}${formattedPlaceName}.jpg` : '/static/icons/default.png';
    
                contenxt += `<div class="swiper-slide" key='${index}' data-name='${placeName}'>
                                <div class="slideItme">
                                    <div class="swperimg">
                                        <img src="${thumbnailUrl}" alt="${placeName}" srcset="">
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
    
                listCont += setMapList({index, thumbnailUrl, placeName});
                orderOfVisit[0].map((item, i) => {
                    if (item === placeName) {
                        addMarkertoMap({ placeName, category: 'dinwei', index, template, description: '', parser, location: orderOfVisit[1][i] })
                        return orderOfVisit[1][i]
                    }
                })
            });
            swiperconent.innerHTML = contenxt;
            poiList.innerHTML = listCont;
        });
        // prompt suggestion if not recent:
        const placeNames = [];
        const coordinates = [];

        Object.keys(placeInfoResponse).forEach(placeName => {
            placeNames.push(placeName);
            coordinates.push(placeInfoResponse[placeName].location);
        });

        const lastEventCheckTime = localStorage.getItem('lastEventCheckTime');
        const currentTime = new Date().getTime();

        if (!lastEventCheckTime || (currentTime - lastEventCheckTime > 5 * 60 * 1000)) {
            // Time difference is more than 5 minutes or this is the first time running

            let nextResponse = await fetch('/check_events', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ places: placeNames, coordinates: coordinates })
            });

            if (nextResponse.status === 204) {
                console.log('No events found for the provided places.');
                return;
            }

            if (!nextResponse.ok) {
                throw new Error('Network response was not ok ' + nextResponse.statusText);
            }

            let nextData = await nextResponse.json();
            if (!chatMessages) {
                var chatMessages = document.getElementById("chatbot-messages");
            }
            if (nextData.response) {
                appendMessage({
                    text: nextData.response,
                    chatMessages,
                    type: 'message',
                    placeNames: nextData.found_places,
                    longAndlat: nextData.coordinates,
                    fromUser: '1',
                });

                attachEventListenersToHyperlinks();
            }
            // if chat box not open, show pop up
            const popupModal = document.getElementById('popupModal');
            if (window.getComputedStyle(popupModal).display == 'none') {
                idaeBox.classList.add('fadeshowin');
            }
            // Update the last event check timestamp
            localStorage.setItem('lastEventCheckTime', currentTime);
        } else {
            console.log('Skipping event check. Less than 5 minutes since the last check.');
        }
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
const foodBox = document.getElementById('foodBox');
const idaeBox = document.getElementById('idaeBox');
const startNav = document.getElementById('startNav');
const totMinus = document.getElementById('totMinus');
const totDist = document.getElementById('totDist');
const chatbotArea = document.getElementById('chatbot-area');
const navcompleted = document.getElementById('navcompleted');
const listButton = document.getElementsByClassName('mapandlistbut')[0]

function setMapList({index, placeName, thumbnailUrl}) {
    return `<div class="itemSlide" key='${index}' data-name='${placeName}'>
        <div class="listimg">
            <img src="${thumbnailUrl}" alt="${placeName}" width="100%" srcset="">
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
    </div>`;
}

window.onload = function () {
    window.mapMarkers = {};
    const tishiDom = document.getElementById('tishi')
    isFirstOpen = localStorage.getItem('isFirstOpen')
    const popupModal = document.getElementById('popupModal');
    const btn = document.getElementById("robotIcoId");
    const stopNav = document.getElementById('closedBut')

    stopNav.onclick = function () {
        stopNavFunc();
    }

    pauseAndpaly.onclick = function () {
        if (simulationRunning) {
            pauseSimulation();
        } else {
            //simulateUserLocation(route);
        }
    }

    btn.onclick = function () {
        popupModal.style.display = "block";
        tishiDom.style.display = "none";
        localStorage.setItem('isFirstOpen', true)
        foodBox.classList.remove('fadeshowin');
        idaeBox.classList.remove('fadeshowin');
        chatbotArea.scrollTop = chatbotArea.scrollHeight;
        const chatMessagesBox = document.getElementById("chatbot-messages");
        chatMessagesBox.scrollTop = chatMessagesBox.scrollHeight;
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
    window.addEventListener('deviceorientation', debounce(function (event) {
        console.log("User facing direction changed.")
        const alpha = event.alpha;
        if (userMarker && event.alpha !== null) {
            const markerElement = userMarker.getElement().getElementsByClassName('user-location-marker')[0]
            markerElement.style.transform = `rotate(${alpha}deg)`
        }
    }, 200));
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
        simulationPaused = false;
        if (window.mapMarkers) {
            for (const [key, value] of Object.entries(window.mapMarkers)) {
                value.remove();
            }
        }
        pauseAndpaly.style.display = 'none';
        const swiperconent = document.getElementById('swiperconent');
        const place = swiperconent.querySelector(`div[key='${swiper.activeIndex}']`).getAttribute('data-name');
        getPlaceCoordWithName(place);
    });
    window.addEventListener('beforeunload', function (event) {
        // confimration to leave page
        event.preventDefault();
    });
}

function debounce(fn, delay) {
    let timer;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delay);
    };
}

function stopNavFunc() {
    closedNavfun();
    poiSwiper.classList.remove('fadeshowin');
    listButton.style.display = 'block';
    pauseAndpaly.style.display = 'none';
    disableNavigationMode();
    simulationRunning = false;
    simulationPaused = false;
    initProperty()
}

function exitNavFunc() {
    closedNavfun();
    poiSwiper.classList.remove('fadeshowin');
    listButton.style.display = 'block';
    navcompleted.classList.remove('fadeshowin');
    navcompleted.classList.add('fadeout');
    disableNavigationMode();
}

function domeShowBootFuc() {
    foodBox.classList.add('fadeshowin');
    // getSuggestion(1);
}

async function getPlaceCoordWithName(place, isNotMarker) {
    if (!isNotMarker) {
        disableNavigationMode();
        closedNavfun();
        if (map.getSource('route')) {
            map.removeLayer('route');
            map.removeSource('route');
            if (map.getLayer('directions')) {
                map.removeLayer('directions');
            }
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
    if (!isNotMarker) {
        map.flyTo({
            center: waypoints[0],
            essential: true
        });
    }
    addMarkers([place], waypoints);
    return responseData
}

function systemQuestionFunc(e) {
    const chatMessages = document.getElementById("chatbot-messages");
    postMessage(e.target.innerText, chatMessages);
}

function showMapTab() {
    mapEl.style.display = 'block';
    poiList.style.display = 'none';
    tabList.classList.remove('activeButton');
    tabMap.classList.add('activeButton');
}

function navDitle(e, name) {
    getPlaceCoordWithName(name);
    showMapTab();
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

fetch('/config')
    .then(response => response.json())
    .then(data => {
        // Assuming the response contains a JSON object with an 'accessToken' property
        mapboxgl.accessToken = data.config.MAPBOX_ACCESS_TOKEN;
        thumbnailURI = data.config.THUMBNAIL_URI;
        const center = [103.827973, 1.250277]
        map = new mapboxgl.Map({
            container: 'map',
            style: 'mapbox://styles/mapbox/streets-v12',
            //style: 'mapbox://styles/wangchongyu86/clp0j9hcy01b301o44qt07gg1',
            //center: [103.8285654153839, 1.24791502223719],
            center,
            zoom: 13,
            minZoom: 10,
        });

        directions = new MapboxDirections({
            accessToken: mapboxgl.accessToken,
            unit: 'metric',
            profile: 'mapbox/walking'
        });
        const navControl = new mapboxgl.NavigationControl({
            showCompass: true,  // Show compass (default is true)
            showZoom: false,
            rotateInner: true,
            showDigit: true
        });
        map.addControl(navControl, 'top-right')
        // variable to allow resizing function
        window.mapboxMap = map;
        const bounds = [
            [103.6, 1.2],  // 西南角 (大致在西南海域)
            [104.1, 1.5]   // 东北角 (大致在东北海域)
        ];
        map.setMaxBounds(bounds);
        map.on('load', function () {
            // Define and set bounds for the map
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
            // geolocation tracking
            geolocateControl = new mapboxgl.GeolocateControl({
                positionOptions: {
                    enableHighAccuracy: true,
                    timeout: 3000,                 // Maximum time (in ms) allowed to get a new location
                    maximumAge: 0                  // Prevents caching of location
                },
                trackUserLocation: true,
                showUserHeading: true, // If you want to show user's heading direction
            });
            // force mapbox to stop changing map view when geolocating
            geolocateControl._updateCamera = () => { }
            map.loadImage('static/icons/walked.png', function (err, image) {
                if (err) {
                    console.error('Error loading image:', err);
                    reject(err);
                }
                map.addImage('walkedArrow', image);
            });
            setTimeout(() => {
                geolocateControl.trigger();
            }, 100)
            // geolocate event 
            const userLoc = [userLocation.lng, userLocation.lat];
            setUserLocationMark(userLoc);
            geolocateControl.on('trackuserlocationstart', () => {
                map.easeTo({
                    center: [userLocation.lng, userLocation.lat],
                    bearing: userLocation.userHeading,  // Set the map's bearing to the user's heading
                    zoom: isUserRunning ? 20 : 13,     // Keep the current zoom level
                    duration: 500         // Animation duration (optional)
                });
            });
            // Add the Geolocate Control to the map
            map.addControl(geolocateControl);
        });
    })
    .catch(error => {
        console.error('Error fetching the access token:', error);
    });

// Function to generate the route and return the route object using async/await
async function getRouteObject(userLocation) {
    try {
        // Call genRoute and wait for the result (route object)
        const result = await genRoute(userLocation);
        return result.route; // Return the route object directly
    } catch (error) {
        console.error('Error fetching route object:', error);
        throw error; // Rethrow the error for higher-level handling
    }
}
// Navigation Mode 
function enableNavigationMode(data) {
    instructions = getInstructions(data);
    document.getElementById('popupModal').style.display = "none";
    const geolocate = document.getElementsByClassName('mapboxgl-ctrl-top-right')[0]
    geolocate.style.top = '210px'
    isUserRunning = true
    const instructionPopup = document.getElementById('navigation');
    if (routeIndex == 0) {
        const firstInstruction = instructions[0];
        // Extract the relevant information for the first instruction
        const instructionTextContent = firstInstruction.instruction; // Text instruction
        const distanceToCheckpoint = firstInstruction.distance; // Distance to the next checkpoint
        const remainingDistance = calculateRemainingDistance(route.coordinates); // Assuming you have a function to calculate total remaining distance
        const modifier = firstInstruction.modifier; // Modifier for direction icons (left, right, etc.)
        // Display the first instruction
        displayInstruction(instructionTextContent, distanceToCheckpoint, remainingDistance, modifier);
    }
    // Show the pop-up
    instructionPopup.classList.add('fadeshowin');
    poiSwiper.classList.add('fadeshowin');
    listButton.style.display = 'none';
    // pauseAndpaly.style.display = 'block';
    // Animate the map to tilt and zoom for 3D perspective
    map.easeTo({
        pitch: 60, // Tilts the map to 60 degrees for a 3D perspective
        zoom: 20,  // Adjust the zoom level for better street view navigation
        center: [userLocation.lng, userLocation.lat], // Center map on user's location
        duration: 500 // Animation duration in milliseconds
    });

    // Wait for easeTo animation to complete, then start tracking
    map.once('moveend', () => trackUserLocation(route));
}
// Function to check if user is off-route
function isUserOffRoute(userLocation, route, tolerance = 0.02) {
    const userCoordinates = [userLocation.lng, userLocation.lat];
    // Extract the coordinates from the route object
    const routeCoordinates = route.coordinates;
    // Create a turf lineString from route coordinates
    const routeLine = turf.lineString(routeCoordinates);

    // Create a buffered area around the route with the specified tolerance
    const bufferedRoute = turf.buffer(routeLine, tolerance, { units: 'kilometers' });

    // Create a point from the user's location
    const userPoint = turf.point(userCoordinates);

    // Check if the user's point is within the buffered route
    return !turf.booleanPointInPolygon(userPoint, bufferedRoute);
}


// Handle route recalculation when user goes off-route
function recalculateRoute(currentLocation, destination) {
    const directionsRequest = `https://api.mapbox.com/directions/v5/mapbox/walking/${currentLocation.lng},${currentLocation.lat};${destination[0]},${destination[1]}s?geometries=geojson&steps=true&access_token=${mapboxgl.accessToken}`;

    fetch(directionsRequest)
        .then(response => response.json())
        .then(data => {
            const newRoute = data.routes[0].geometry.coordinates;
            // replace and reset all route memory objects
            route = data.routes[0].geometry;
            steps = data.routes[0].legs[0].steps;
            walkStepsNavs = data;
            instructions = getInstructions(steps);
            routeIndex = 0;
            // Update the map with new route
            if (map.getSource('route')) {
                map.getSource('route').setData({
                    'type': 'Feature',
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': newRoute
                    }
                });
            }
            // restart tracking:
            trackUserLocation(route);
            if (!isUserRunning) {
                paintLine(route, false)
            } else {
                setDottedLine()
            }
            console.log("New route calculated and updated on the map.");
        })
        .catch(error => console.error('Error in recalculating route:', error));
}
function setUserLocationMark(coord, angle) {
    if (userMarker) {
        userMarker.remove()
        userMarker = null
    }
    const el = document.createElement('div');
    el.insertAdjacentHTML('beforeend', `<div class='user-location-marker'></div>`);
    userMarker = new mapboxgl.Marker({
        rotationAlignment: 'map',
        element: el
    })
        .setLngLat(coord)
        .addTo(map);
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
function updateNavigationInstructions(userLocation) {
    const thresholdDistance = 5;
    // Calculate the distance between the user's current location and the next checkpoint
    const checkpoint = {
        lng: steps[currentStepIndex].maneuver.location[0],
        lat: steps[currentStepIndex].maneuver.location[1]
    };
    const distanceToCheckpoint = calculateDistance(userLocation, checkpoint);
    console.log("Currently tracking checkpoint: " + JSON.stringify(checkpoint));

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

// Function to use user's current location and update their position along the route
function trackUserLocation(route) {
    console.log("Tracking user location");
    const imgs = pauseAndpaly.getElementsByTagName('img')[0];
    imgs.setAttribute('src', `static/icons/pause.svg`);

    // Set the user's initial location marker at the starting point
    walkedRoute.unshift(route.coordinates[0]);
    // Function to handle location updates from the GeolocateControl
    function updateLocation(position) {
        if (!simulationRunning) return;
        const currentPosition = {
            lng: position.coords.longitude,
            lat: position.coords.latitude
        };
        const nextPosition = {
            lng: route.coordinates[routeIndex + 1][0],
            lat: route.coordinates[routeIndex + 1][1]
        };
        debounce(() => {
            getPoisByLocation(currentPosition);
        }, 5000)
        // Update the user's location in your app
        updateUserLocation(currentPosition);

        // Update the marker position to the user's current location
        userMarker.setLngLat([currentPosition.lng, currentPosition.lat]);

        // Calculate remaining distance to the next position on the route
        const remainingDistance = distanceBetweenPoints([currentPosition.lng, currentPosition.lat], [nextPosition.lng, nextPosition.lat]);

        updateWalkedRoute([currentPosition.lng, currentPosition.lat]);
        updateRemainingRoute([currentPosition.lng, currentPosition.lat]);

        // If the remaining distance is less than the threshold, move to the next point
        if (remainingDistance <= targetDistance) {
            routeIndex++;

            if (routeIndex >= route.coordinates.length - 1) {
                // Route completed
                closedNavfun();
                navcompleted.classList.add('fadeshowin');
                pauseAndpaly.style.display = 'none';
                initProperty();
                console.log("Route tracking completed");
            }
        }

        // Update navigation instructions based on the user's current position
        updateNavigationInstructions(currentPosition);
    }

    // Event listener for when the user's location changes
    geolocateControl.on('geolocate', (position) => {
        console.log('Updating user location:')
        debounce(() => {
            updateLocation(position);
        }, 100)
    });
}

function updateWalkedRoute(currentPosition) {
    // Add the current position to the walked route
    walkedRoute.push(currentPosition);

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
    const remainingRoute = route.coordinates.slice(routeIndex + 1);
    remainingRoute.unshift(currentPosition);
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
    // Check if the user is off-route after updating the location
    if (isUserOffRoute(userLocation, route)) {
        console.log('User is off-route, recalculating route...');
        recalculateRoute(userLocation, endPlaceProt);  // Call reroute function
    }
}

// Function to pause the simulation
function pauseSimulation() {
    console.log(route)
    if (simulationRunning && !simulationPaused) {
        simulationPaused = true;
        simulationRunning = false;
        const imgs = pauseAndpaly.getElementsByTagName('img')[0]
        imgs.setAttribute('src', `static/icons/continue.svg`);
        console.log("Simulation paused");
    }
}

// Function to stop the simulation
function stopSimulation() {
    simulationRunning = false;
    simulationPaused = false;
    initProperty()
    console.log("Simulation stopped");
}

function setMapRoute(resRoute) {
    if (!map.getLayer('route')) {
        map.loadImage(
            'static/icons/nav.png',
            (error, image) => {
                if (error) throw error;
                if (!map.hasImage('arrow')) {
                    map.addImage('arrow', image);
                }
                // Add route to map
                if (!map.getSource('route')) {
                    map.addSource('route', {
                        'type': 'geojson',
                        'data': {
                            'type': 'Feature',
                            'properties': {},
                            'geometry': resRoute
                        }
                    });
                }
                map.addLayer({
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
        directions.on('route', function (e) {
            const route = e.route[0].geometry;
            map.getSource('route').setData(route);
        });
    }

    if (!map.getSource('walked-route')) {
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
    }

    if (!map.getLayer('walked-route')) {
        map.addLayer({
            "id": "walked-route",
            "type": "symbol",
            "source": "walked-route",
            'layout': {
                'symbol-placement': 'line',
                'symbol-spacing': 2,
                'icon-image': 'walkedArrow',
                'icon-size': 0.5,
                'icon-allow-overlap': true,
            },
        });
    }
}

function userCalculate(start, end) {
    const startLat = start[1] * Math.PI / 180;
    const startLng = start[0] * Math.PI / 180;
    const endLat = end[1] * Math.PI / 180;
    const endLng = end[0] * Math.PI / 180;

    const dJiaodiLng = endLng - startLng;
    const y = Math.sin(dJiaodiLng) * Math.cos(endLat);
    const x = Math.cos(startLat) * Math.sin(endLat) -
        Math.sin(startLat) * Math.cos(endLat) * Math.cos(dJiaodiLng);
    const bearing = Math.atan2(y, x) * 180 / Math.PI;

    return (bearing + 360) % 360; // 确保角度在0-360之间
}

function paintLine(resRoute, isZoom = true) {
    showMapTab();
    let bers = 0;
    const startPrit = [userLocation.lng, userLocation.lat];
    let endProit = []
    if (resRoute && resRoute.coordinates && resRoute.coordinates.length) {
        endProit = resRoute.coordinates[resRoute.coordinates.length - 1]
        bers = userCalculate(resRoute.coordinates[0], endProit);
        setDottedLine()
    }
    if (!map.getSource('previewRoute')) {
        map.addSource('previewRoute', {
            'type': 'geojson',
            'data': {
                'type': 'Feature',
                'properties': {},
                'geometry': resRoute,
            }
        });
    } else {
        map.getSource('previewRoute').setData({
            "type": "Feature",
            "geometry": resRoute,
        });
    }
    if (!map.getLayer('prewroute')) {
        // 添加边框图层
        map.addLayer({
            id: 'lineBorder',
            type: 'line',
            source: 'previewRoute',
            layout: {
                'line-join': 'round',
                'line-cap': 'round'
            },
            paint: {
                'line-color': '#fff',
                'line-width': 12
            }
        });
        map.addLayer({
            id: 'prewroute',
            type: 'line',
            source: 'previewRoute',
            layout: {
                'line-join': 'round',
                'line-cap': 'round'
            },
            paint: {
                'line-color': '#00ADE9',
                'line-width': 7,
                'line-opacity': 1,
            }
        });
    }
    if (!isZoom) return
    map.fitBounds([startPrit, endProit], {
        // bearing: bers,
        padding: 50, // 距离屏幕边缘的内边距（以像素为单位）
        maxZoom: 16,
        duration: 1000
    });
}

function setDottedLine() {
    if (walkStepsNavs && walkStepsNavs.waypoints.length) {
        const userfirstDistance = walkStepsNavs.waypoints[0].distance
        if (userfirstDistance > 5) {
            const geometry = {
                coordinates: [
                    [userLocation.lng, userLocation.lat],
                    walkStepsNavs.waypoints[0].location
                ],
                type: "LineString",
            }
            if (!map.getSource('dottedLine')) {
                map.addSource('dottedLine', {
                    'type': 'geojson',
                    'data': {
                        'type': 'Feature',
                        'properties': {},
                        'geometry': geometry,
                    }
                });
            } else {
                map.getSource('dottedLine').setData({
                    "type": "Feature",
                    "geometry": geometry,
                });
            }
            if (!map.getLayer('dottedLineroute')) {
                map.addLayer({
                    id: 'dottedLineroute',
                    type: 'line',
                    source: 'dottedLine',
                    layout: {
                        'line-join': 'round',
                        'line-cap': 'round'
                    },
                    paint: {
                        'line-color': '#4a5367',
                        'line-width': 5,
                        'line-dasharray': [2, 2]
                    }
                });
            }
        } else if (map.getLayer('dottedLineroute')) {
            map.removeLayer('dottedLineroute');
        }
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
        endPlaceProt = rawCoordinates;
        // Check number of waypoints. If less than 25, execute the usual. Else, fetch centroids.
        let allCoordinates;
        if (fromUser) {
            allCoordinates = [[userLocation.lng, userLocation.lat], ...rawCoordinates];
        } else {
            allCoordinates = rawCoordinates;
        }
        const coordinates = allCoordinates.map(coord => coord.join(',')).join(';');
        console.log("Coordinates to go to: " + coordinates, rawCoordinates)
        // Process fetched directions data or centroids
        getMapboxWlakRoute(coordinates)
            .then(result => {
                let cneterPot = [userLocation.lng, userLocation.lat]
                if (result.legs && result.route) {
                    geolocateControl.on('geolocate', (position) => {
                        userLocation = {
                            lng: position.coords.longitude,
                            lat: position.coords.latitude,
                            userHeading: position.coords.heading,
                        };
                        setUserLocationMark([position.coords.longitude, position.coords.latitude]);
                        setDottedLine()
                        if (isUserOffRoute(userLocation, result.route)) {
                            console.log('User is off-route, recalculating route...');
                            recalculateRoute(userLocation, endPlaceProt);  // Call reroute function
                        }
                    });
                    // console.log('------result->>>>>>>>>', result)
                    // Extract route instructions
                    if (result.route.coordinates && result.route.coordinates.length) {
                        cneterPot = result.route.coordinates[Math.floor(result.route.coordinates.length * 0.5)]
                    }
                    var instructions = extractRouteInstructions(result.legs, placeNames);
                    resolve(instructions);
                } else if (result.newUrl) {
                    // Handle URL for later use case
                    resolve(result.newUrl);
                } else {
                    throw new Error('Invalid data received');
                }
                map.flyTo({
                    center: cneterPot,
                    essential: true, // This ensures the animation happens even with prefers-reduced-motion
                    zoom: 14 // Increase the zoom level as needed
                });
            })
            .catch(error => {
                console.error('Error processing route or centroids:', error);
                reject(error);
            });
    });
}

function getMapboxWlakRoute(coordinates) {
    const url = `https://api.mapbox.com/directions/v5/mapbox/walking/${coordinates}?geometries=geojson&steps=true&access_token=${mapboxgl.accessToken}`;
    return fetch(url)
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to fetch route data');
            }
            return response.json();
        })
        .then(data => {
            if (data.routes && data.routes.length > 0) {
                initProperty();
                const legs = data.routes[0].legs;
                api_response = data.routes[0]
                // console.log('------data->>>>>>>>>', data)
                const totalDistance = legs[0].distance.toFixed(2);
                const totalDuration = legs[0].duration;
                if (totMinus && totDist) {
                    totMinus.innerText = `${Math.ceil(totalDuration / 60)}min`
                    totDist.innerText = totalDistance > 1000 ? `${(totalDistance / 1000).toFixed(2)}km` : `${totalDistance}m`
                }
                route = data.routes[0].geometry;
                steps = data.routes[0].legs[0].steps;
                walkStepsNavs = data
                return { legs, route };
            } else {
                console.error('No route found: ', data);
                throw new Error('No route found');
            }
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

function submitChat(event) {
    if (event.key === "Enter") {
        event.preventDefault();
        var inputBox = document.getElementById("chatbot-input");
        var message = inputBox.value;

        if (message !== "") {
            var chatMessages = document.getElementById("chatbot-messages");
            postMessage(message, chatMessages);
            // Start the timer if not running
            // if (!suggestionTimer) {
            //     resetTimer();  // Replace "someType" with the actual type if needed
            // }
            inputBox.value = "";
        }
    }
}
// Chat timer: track time since last message
function resetTimer() {
    // Clear any existing timer
    if (suggestionTimer) {
        console.log("Resetting suggstion timer.")
        clearTimeout(suggestionTimer);
    }
    console.log("Starting a timer for suggestions.")
    // Set a new timer that runs after 5 minutes
    suggestionTimer = setTimeout(() => {
        console.log("5 minutes since last message, prompting suggestions.")
        // getSuggestion(3);  // Trigger suggestion after 5 minutes of inactivity
        // getSuggestion(4);  // recommend another food.beverage option for 2nd demo.
        clearTimeout(suggestionTimer);  // Stop the timer after suggestion is made
        suggestionTimer = null;  // Set timer to null, so it can be started again
    }, suggestionTimeout);
}

async function postMessage(message, chatMessages) {
    appendMessage({ text: message, className: 'visitor-message', chatMessages });
    appendMessage({ text: null, chatMessages });
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
            let textResponse = await fetch('/get_text', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ route: orderOfVisit[0], message: message, coordinates: orderOfVisit[1] })
            });
            if (!textResponse.ok) {
                throw new Error('Network response was not ok ' + textResponse.statusText);
            }
            let textData = await textResponse.json();
            appendMessage({
                text: textData.response,
                chatMessages,
                type: 'route',
                placeNames: orderOfVisit[0],
                longAndlat: orderOfVisit[1],
                fromUser: '1',
            });
            attachEventListenersToHyperlinks();
            // let nextResponse = await fetch('/check_events', {
            //     method: 'POST',
            //     headers: {
            //         'Content-Type': 'application/json'
            //     },
            //     body: JSON.stringify({ places: orderOfVisit[0], coordinates: orderOfVisit[1] })
            // });

            // Check if the response status is 204 (No Content)
            if (nextResponse.status === 204) {
                // Do nothing if the response is empty
                console.log('No events found for the provided places.');
                return;  // Exit early
            }

            // Proceed if the response is ok and not empty
            if (!nextResponse.ok) {
                throw new Error('Network response was not ok ' + nextResponse.statusText);
            }

            let nextData = await nextResponse.json();  // Retrieve the JSON data from the response

            // Check if the response contains the necessary data and append the message
            if (nextData.response) {
                appendMessage({
                    text: nextData.response,
                    chatMessages,
                    type: 'message',
                    placeNames: nextData.found_places,  // Use found_places from the response
                    longAndlat: nextData.coordinates,   // Use coordinates from the response
                    fromUser: '1',
                });

                // Attach event listeners to the hyperlinks
                attachEventListenersToHyperlinks();
            }

        } else if (data.operation == "location") {
            let cleanedPlaceNames = data.response;

            console.log(cleanedPlaceNames); // Check the cleaned list
            // Get the route from the get_coordinates function
            let orderOfVisit = await get_coordinates_without_route(cleanedPlaceNames);
            addMarkers(orderOfVisit[0], orderOfVisit[1]);
            console.log("Location op POIs: " + orderOfVisit)
            let textResponse = await fetch('/get_text', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ route: orderOfVisit[0], message: message, coordinates: orderOfVisit[1] })
            });
            if (!textResponse.ok) {
                throw new Error('Network response was not ok ' + textResponse.statusText);
            }
            let textData = await textResponse.json();
            appendMessage({
                text: textData.response,
                chatMessages,
                type: 'location',
                placeNames: orderOfVisit[0],
                longAndlat: orderOfVisit[1],
            });
            attachEventListenersToHyperlinks();
            // let nextResponse = await fetch('/check_events', {
            //     method: 'POST',
            //     headers: {
            //         'Content-Type': 'application/json'
            //     },
            //     body: JSON.stringify({ places: orderOfVisit[0], coordinates: orderOfVisit[1] })
            // });

            // Check if the response status is 204 (No Content)
            if (nextResponse.status === 204) {
                // Do nothing if the response is empty
                console.log('No events found for the provided places.');
                return;  // Exit early
            }

            // Proceed if the response is ok and not empty
            if (!nextResponse.ok) {
                throw new Error('Network response was not ok ' + nextResponse.statusText);
            }

            let nextData = await nextResponse.json();  // Retrieve the JSON data from the response

            // Check if the response contains the necessary data and append the message
            if (nextData.response) {
                appendMessage({
                    text: nextData.response,
                    chatMessages,
                    type: 'message',
                    placeNames: nextData.found_places,  // Use found_places from the response
                    longAndlat: nextData.coordinates,   // Use coordinates from the response
                    fromUser: '1',
                });

                // Attach event listeners to the hyperlinks
                attachEventListenersToHyperlinks();
            }
        } else if (data.operation == "wayfinding") {
            console.log("PLaces: " + data.response);
            let cleanedPlaceNames = data.response;

            console.log(cleanedPlaceNames); // Check the cleaned list
            // Get the route from the get_coordinates function
            let orderOfVisit = await get_coordinates(cleanedPlaceNames, true);
            addMarkers(orderOfVisit[0], orderOfVisit[1]);
            let textResponse = await fetch('/get_text', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ route: orderOfVisit[0], message: message, coordinates: orderOfVisit[1] })
            });
            if (!textResponse.ok) {
                throw new Error('Network response was not ok ' + textResponse.statusText);
            }
            let textData = await textResponse.json();
            appendMessage({
                text: textData.response,
                chatMessages,
                type: 'route',
                placeNames: orderOfVisit[0],
                longAndlat: orderOfVisit[1],
            });
            attachEventListenersToHyperlinks();
            // let nextResponse = await fetch('/check_events', {
            //     method: 'POST',
            //     headers: {
            //         'Content-Type': 'application/json'
            //     },
            //     body: JSON.stringify({ places: orderOfVisit[0], coordinates: orderOfVisit[1] })
            // });

            // Check if the response status is 204 (No Content)
            if (nextResponse.status === 204) {
                // Do nothing if the response is empty
                console.log('No events found for the provided places.');
                return;  // Exit early
            }

            // Proceed if the response is ok and not empty
            if (!nextResponse.ok) {
                throw new Error('Network response was not ok ' + nextResponse.statusText);
            }

            let nextData = await nextResponse.json();  // Retrieve the JSON data from the response

            // Check if the response contains the necessary data and append the message
            if (nextData.response) {
                appendMessage({
                    text: nextData.response,
                    chatMessages,
                    type: 'message',
                    placeNames: nextData.found_places,  // Use found_places from the response
                    longAndlat: nextData.coordinates,   // Use coordinates from the response
                    fromUser: '1',
                });

                // Attach event listeners to the hyperlinks
                attachEventListenersToHyperlinks();
            }
        } else {
            appendMessage({ text: data.response, chatMessages });
        }
    } catch (error) {
        console.error('Error:', JSON.stringify(error));
    }
}

function disminiNav() {
    startNav.classList.add('fadeshowin');
    poiSwiper.classList.remove('fadeshowin');
    navcompleted.classList.remove('fadeshowin');
    navcompleted.classList.add('fadeout');
}

async function navFunc(e, typeSuge, place, longAndlat, fromUser) {
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
    paintLine(route)
}

function closedNavfun() {
    const navigationElem = document.getElementById('navigation');
    navigationElem.classList.remove('fadeshowin');
    navigationElem.classList.add('fadeout');
    if (map.getLayer('route')) {
        map.removeLayer('route');
    }
    if (map.getSource('route')) {
        map.removeSource('route');
    }
    if (map.getLayer('walked-route')) {
        map.removeLayer('walked-route');
    }
    if (map.getSource('walked-route')) {
        map.removeSource('walked-route');
    }
    if (map.getLayer('prewroute')) {
        map.removeLayer('prewroute');
    }
    if (map.getLayer('lineBorder')) {
        map.removeLayer('lineBorder');
    }
    if (map.getLayer('dottedLineroute')) {
        map.removeLayer('dottedLineroute');
    }
    const geolocate = document.getElementsByClassName('mapboxgl-ctrl-top-right')[0]
    geolocate.style.top = '80px'
    isUserRunning = false
}

// creaate template and styles for each visitor/guide message.
function appendMessage({ text, className, chatMessages, type, suggestion, placeNames, longAndlat, fromUser }) {
    let long = ''
    if (longAndlat && Array.isArray(longAndlat) && longAndlat.length && Array.isArray(longAndlat[0])) {
        long = longAndlat[0].join(',')
    }
    const currClass = className || 'guide-message'
    if (!className) {
        if (!text) {
            chatMessages.innerHTML += `<div id='loading' class='chat-message ${currClass}'>
                <div class='guideImage'><img src="static/icons/choml.png" alt="" srcset=""></div>
                <div class='guideText'>
                    <div class='messageStype'>
                        <div class="dots">
                        <div></div>
                        <div></div>
                        <div></div>
                        </div>
                    </div>
                </div>
            </div>
            `
            return;
        } else {
            const bloaDox = document.getElementById("loading");
            if (bloaDox) {
                bloaDox.remove();
            }
        }
        if ((type === 'route' || type === 'location') && !(placeNames && placeNames.length > 1)) {
            chatMessages.innerHTML += `<div class='chat-message ${currClass}'>
            <div class='guideImage'><img src="static/icons/choml.png" alt="" srcset=""></div>
            <div class='guideText'>
                <div class='messageStype'>
                    ${text}
                    <p style='margin-top: 10px;'>
                        <button id="takeThereBut" onclick="navFunc(event, '${suggestion}', '${placeNames ? placeNames[0] : ''}', '${long}', '${fromUser}')">
                            <img src="static/icons/daohang.svg" alt="" srcset="">
                            <span>Take me there</span>
                        </button>
                    </p>
                </div>
            </div>
        </div>
        `
        } else {
            chatMessages.innerHTML += `<div class='chat-message ${currClass}'>
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
        chatMessages.innerHTML += `<div class='chat-message ${currClass}'>${marked.parse(text)}</div>`
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

async function getCoordinatesWithPlace(places) {
    console.log('===places=>>>', places);
    try {
        const response = await fetch('/get_coordinates', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                places,
            })
        });

        if (!response.ok) {
            throw new Error('Network response was not ok ' + response.statusText);
        }

        const responseData = await response.json();
        const coordinates = responseData.coordinates;
        const placeNames = responseData.places && responseData.places.length ? responseData.places : places;

        // Map coordinates to waypoints
        const waypoints = coordinates.map(coord => [coord.lng, coord.lat]);

        // Optimize the route: input: (placeNames, waypoints) output: re-ordered version of input in sequence of visit
        let orderOfVisit = await optimizeRoute(placeNames, waypoints);
        console.log('===orderOfVisit=>>>', orderOfVisit);
        return orderOfVisit;
    } catch (error) {
        console.error('Error fetching coordinates:', error);
    }
}

async function get_coordinates(data, fromUser) {
    const orderOfVisit = await getCoordinatesWithPlace(data);
    return orderOfVisit;
}

async function get_coordinates_without_route(data) {
    const orderOfVisit = await getCoordinatesWithPlace(data);
    return orderOfVisit;
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
            const parser = new DOMParser();
            placeNames.forEach((placeName, index) => {
                var coord = waypoints[index];
                if (!coord || coord.length !== 2 || isNaN(coord[0]) || isNaN(coord[1])) {
                    console.error(`Invalid coordinates for ${placeName}:`, coord);
                    return; // Skip this iteration if coordinates are invalid
                }
                const  description = placesData[placeName] ? placesData[placeName]['description'] : ''
                addMarkertoMap({ placeName, category: 'dinwei', index, template, description, parser, location: coord })
            });
        });
    });
}

function displayByCategory(category, element) {
    const munts = document.getElementsByClassName('newHeader')[0]
    const lis = munts.getElementsByClassName('item')
    for (let index = 0; index < lis.length; index++) {
        const item = lis[index];
        item.classList.remove('active')
    }
    element.classList.add('active');
    // Remove existing markers from the map
    if (window.mapMarkers) {
        for (const [key, value] of Object.entries(window.mapMarkers)) {
            value.remove();
        }
    }
    window.mapMarkers = {};

    // Fetch places data by category from the Flask endpoint
    fetch('/fetch_by_category', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ category }),
    })
        .then(response => response.json())
        .then(placesData => {
            fetchTemplate('static/html/info-card.html').then(template => {
                const parser = new DOMParser();
                let listCont = ''
                // Loop through the placesData and place markers on the map
                Object.entries(placesData).forEach(([placeName, placeInfo], index) => {
                    const { description, location } = placeInfo;
                    // Ensure location contains valid coordinates [longitude, latitude]
                    if (!location || location.length !== 2 || isNaN(location[0]) || isNaN(location[1])) {
                        console.error(`Invalid coordinates for ${placeName}:`, location);
                        return; // Skip this iteration if coordinates are invalid
                    }
                    listCont += addMarkertoMap({ placeName, category, index, template, description, parser, location })
                });
                poiList.innerHTML = listCont;
            });
        })
        .catch(error => {
            console.error('Error fetching places data:', error);
        });
}

function addMarkertoMap({ placeName, category, index, template, description, parser, location }) {
    // Remove unwanted characters from the placeName
    placeName = placeName.replace(/[\[\]]/g, '');
    console.log(placeName);

    // Set up the basic place information
    const place = {
        description: description || '',
        name: placeName,
    };

    // Create the thumbnail URL using Google Cloud Storage
    let formattedPlaceName = placeName.toLowerCase().replace(/\s+/g, '-');
    if (formattedPlaceName.toLowerCase().includes("toilet")) {
        formattedPlaceName = "toilet";
    } else if (formattedPlaceName.toLowerCase().includes("station")) {
        formattedPlaceName = "station";
    }
    const thumbnailUrl = `${thumbnailURI}${formattedPlaceName}.jpg`;
    place.thumbnail = thumbnailUrl || '/static/icons/default.png'; // Fallback if no thumbnail is found

    // Generate the popup content using the template
    const popupContentString = populateTemplate(template, place);
    const doc = parser.parseFromString(popupContentString, 'text/html');
    const popupContent = doc.querySelector('.info-card-content');
    // Add functionality for the button in the popup
    popupContent.querySelector('button').onclick = async function () {
        disminiNav();
        await displayRoute([placeName], [location], true);
        paintLine(route);
    };

    // Create a popup and marker for the map
    const popupId = placeName.replace(/\s+/g, '-').toLowerCase();
    const popup = new mapboxgl.Popup().setDOMContent(popupContent);

    const el = document.createElement('div');
    el.insertAdjacentHTML('beforeend', `<p><img src="static/icons/${category}_maker.svg" width="46" alt="" srcset=""></p>`);
    const marker = new mapboxgl.Marker({
        element: el
    })
        .setLngLat([location[0], location[1]]) // Use location from the placeInfo
        .setPopup(popup)
        .addTo(map);
    // Store marker by ID
    window.mapMarkers[popupId] = marker;
    return setMapList({index, thumbnailUrl: place.thumbnail, placeName});
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

// Add event listeners to the hyperlinks
function attachEventListenersToHyperlinks() {
    document.querySelectorAll('.location-link').forEach(function (link) {
        link.addEventListener('click', function (e) {
            showMapTab();
            pauseAndpaly.style.display = 'none';
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

function awaitGetPlaceCoordWithName(place) {
    // Return a promise that resolves when the getPlaceCoordWithName function completes
    return new Promise((resolve, reject) => {
        getPlaceCoordWithName(place, true)
            .then((res) => resolve(res)) // Resolve the promise when getPlaceCoordWithName completes
            .catch(error => reject(error)); // Reject the promise if there’s an error
    });
}

function getPromo() {
    idaeBox.classList.add('fadeshowin');
    // getSuggestion(2);
}

// Suggestion Button:
// EXAMPLE usage of endpoint:
async function getSuggestion(type) {
    if (!chatMessages) {
        var chatMessages = document.getElementById("chatbot-messages");
    }
    try {
        // Send a POST request to the /suggestion endpoint
        const response = await fetch('/suggestion', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ choice: type })
        });

        // Check if the response is OK (status code 200-299)
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        // Parse the JSON response
        const data = await response.json();
        // Check response in console:
        console.log('Response from /suggestion: ', data);
        // Get info of poi and make marker
        suggestionData = await awaitGetPlaceCoordWithName(data.POI);
        //Post the message in chatbox:
        appendMessage({
            text: data.message,
            chatMessages,
            type: 'location',
            suggestion: 'suggestion',
        });
        attachEventListenersToHyperlinks();
    } catch (error) {
        console.error('Error fetching suggestion:', error);
    }
}

// start
function startUserNav() {
    console.log('-----steps-->>>', steps)
    if (map.getLayer('prewroute')) {
        map.removeLayer('prewroute');
    }
    if (map.getLayer('lineBorder')) {
        map.removeLayer('lineBorder');
    }
    setDottedLine()
    setMapRoute(route)
    startNav.classList.remove('fadeshowin');
    enableNavigationMode(steps);
}
function cancelNav() {
    closedNavfun();
    map.easeTo({
        pitch: 0, // Back to 2D top-down view
        bearing: 0,
        zoom: 13, // Adjust zoom level if needed
        duration: 1000
    });
    listButton.style.display = 'block';
    startNav.classList.remove('fadeshowin');
}