import * as Setup from "./map-setup.js";
import * as Chat from "./chat-mod.js";
import * as Promo from "./promo-mod.js";
import * as Nav from "./nav-mod.js";
window.Setup = Setup
window.Chat = Chat
window.Promo = Promo
window.Nav = Nav

export const sharedState = {
    userLocation: null,
    userMarker: null,
    map: null,
    endPlaceProt: null, // end port
    firstClick : false,
    routeIndex: 0,
    steps: null,
    instructions: null,
    currentStepIndex: 0, // Start at the first step of the route
    suggestionData: null,
    walkStepsNavs: null,
    userTouch: false,
    route: {},
    walkedRoute: null,
    geolocateControl: null,
    directions: null,
    isUserRunning: false,
    switchoverState: 'POSINIT',// POSINIT or FOCUS
    hiddenMap: null
};
export let isFirstOpen = false;
export let thumbnailURI;

function normalizeRing(ring) {
    if (!Array.isArray(ring) || ring.length < 3) return null;
    const normalized = ring.map((coord) => [Number(coord[0]), Number(coord[1])]);
    const first = normalized[0];
    const last = normalized[normalized.length - 1];
    if (first[0] !== last[0] || first[1] !== last[1]) {
        normalized.push([first[0], first[1]]);
    }
    return normalized;
}

function buildSpotlightMaskFeature(polygon) {
    if (!polygon || polygon.type !== "Polygon" || !Array.isArray(polygon.coordinates)) {
        return null;
    }
    const worldRing = [
        [-180, -85],
        [180, -85],
        [180, 85],
        [-180, 85],
        [-180, -85],
    ];
    const holeRings = polygon.coordinates
        .map((ring) => normalizeRing(ring))
        .filter((ring) => !!ring);
    if (!holeRings.length) {
        return null;
    }
    return {
        type: "Feature",
        properties: {},
        geometry: {
            type: "Polygon",
            coordinates: [worldRing, ...holeRings],
        },
    };
}

function applySpotlightMask(mapInstance, polygon) {
    if (!mapInstance) return;
    const sourceId = "spotlight-mask";
    const layerId = "spotlight-mask-layer";

    if (mapInstance.getLayer(layerId)) {
        mapInstance.removeLayer(layerId);
    }
    if (mapInstance.getSource(sourceId)) {
        mapInstance.removeSource(sourceId);
    }

    const maskFeature = buildSpotlightMaskFeature(polygon);
    if (!maskFeature) return;

    mapInstance.addSource(sourceId, {
        type: "geojson",
        data: maskFeature,
    });
    mapInstance.addLayer({
        id: layerId,
        type: "fill",
        source: sourceId,
        paint: {
            "fill-color": "#000000",
            "fill-opacity": 0.55,
        },
    });
}

const pauseAndpaly = document.getElementById('pauseAndpaly');
const foodBox = document.getElementById('foodBox');
const idaeBox = document.getElementById('idaeBox');
const chatbotArea = document.getElementById('chatbot-area');
const zoomControls = document.getElementById('zoom-controls');
const dingwenndId = document.getElementById('dingwennd');
export function displayAiModal () {
    const popupModal = document.getElementById('popupModal');
    popupModal.style.display = "none";
}
window.onload = function () {
    Setup.handlePermission();
    console.log("Resetting chat memory")
    fetch("/reset_memory"); // Calls endpoint to reset memory
    window.mapMarkers = {};
    const tishiDom = document.getElementById('tishi')
    isFirstOpen = localStorage.getItem('isFirstOpen')
    const popupModal = document.getElementById('popupModal');
    const btn = document.getElementById("robotIcoId");
    const stopNav = document.getElementById('closedBut')

    stopNav.onclick = function () {
        Nav.stopNavFunc();
    }

    // pauseAndpaly.onclick = function () {
    //     if (simulationRunning) {
    //         pauseSimulation();
    //     } else {
    //         //simulateUserLocation(route);
    //     }
    // }

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
    if (Setup.detectDevice() !== 'Android' && typeof DeviceOrientationEvent.requestPermission === 'function') {
        // iOS 13+ 需要请求权限
        DeviceOrientationEvent.requestPermission()
            .then(response => {
                if (response === 'granted') {
                    window.addEventListener('deviceorientation', handleOrientationChange);
                } else {
                    alert('未授予设备方向传感器权限');
                }
            })
            .catch(console.error);
    } else {
        window.addEventListener('deviceorientation', Setup.debounce(function (event) {
            Setup.handleOrientationChange(event)
        }, 10));
    }
    Setup.getUserCurrentPosition();
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
        Setup.getPlaceCoordWithName(place);
    });
    window.addEventListener('beforeunload', function (event) {
        // confimration to leave page
        event.preventDefault();
    });
}

fetch('/config')
  .then(response => response.json())
    .then(data => {
        mapboxgl.accessToken = data.config.MAPBOX_ACCESS_TOKEN;
        thumbnailURI = data.config.THUMBNAIL_URI;
        let center;
        try {
            center = JSON.parse(data.config.MAP_CENTRE);
            if (!Array.isArray(center) || center.length !== 2) {
                throw new Error("Invalid MAP_CENTRE format");
        }
        } catch (err) {
            console.error("Failed to parse MAP_CENTRE:", err);
            center = [103.8198, 1.3521];  // default fallback center (Singapore)
        }
        let spotlightPolygon = null;
        if (data.config.MAP_SPOTLIGHT_POLYGON) {
            try {
                spotlightPolygon = JSON.parse(data.config.MAP_SPOTLIGHT_POLYGON);
                if (!spotlightPolygon || spotlightPolygon.type !== "Polygon") {
                    spotlightPolygon = null;
                }
            } catch (err) {
                console.error("Failed to parse MAP_SPOTLIGHT_POLYGON:", err);
                spotlightPolygon = null;
            }
        }
        const comfig = {
        style: data.config.MAPBOX_STYLE_URL,
        center,
        zoom: 13,
        minZoom: 10,
        };
        sharedState.hiddenMap = new mapboxgl.Map({
            container: 'hiddenMap',
            ...comfig,
        });
        sharedState.map = new mapboxgl.Map({
            container: 'map',
            ...comfig,
        });
        sharedState.directions = new MapboxDirections({
            accessToken: mapboxgl.accessToken,
            unit: 'metric',
            profile: 'mapbox/walking'
        });
        // variable to allow resizing function
        window.mapboxMap = map;
        fetch("/get_bounds")
            .then(res => res.json())
            .then(data => {
                if (data.bounds) {
                sharedState.map.fitBounds(data.bounds, {
                    padding: 50,
                    maxZoom: 14,     // prevent zooming in too far
                    duration: 1000   // smooth animation
                });

                // Optionally restrict user panning outside this area
                sharedState.map.setMaxBounds(data.bounds);
                }
                if (data.center) {
                    sharedState.map.setCenter([
                      data.center[0],
                      data.center[1]
                    ]);
                }
            });
        const geolocationCogif = {
            positionOptions: {
                enableHighAccuracy: true,
                timeout: 3000,                 // Maximum time (in ms) allowed to get a new location
                maximumAge: 0                  // Prevents caching of location
            },
            trackUserLocation: true,
            showUserHeading: true, // If you want to show user's heading direction
        }
        sharedState.map.on('load', function () {
            // Define and set bounds for the map
            // 3D Layer for navigation view.    
            const navControl = new mapboxgl.NavigationControl({
                showCompass: true,  // Show compass (default is true)
                showZoom: false,
                rotateInner: true,
                showDigit: true
            });
            sharedState.map.addControl(navControl, 'top-right')
            sharedState.map.addLayer({
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
            sharedState.geolocateControl = new mapboxgl.GeolocateControl({ ...geolocationCogif });

            sharedState.map.addControl(sharedState.geolocateControl);
            if (spotlightPolygon) {
                applySpotlightMask(sharedState.map, spotlightPolygon);
            }
            // force mapbox to stop changing map view when geolocating
            sharedState.geolocateControl._updateCamera = () => { }
            sharedState.map.loadImage('static/icons/walked.png', function (err, image) {
                if (err) {
                    console.error('Error loading image:', err);
                    reject(err);
                }
                sharedState.map.addImage('walkedArrow', image);
            });
            function startCheckingNearbyEvents() {
                function checkAndRepeat() {
                    navigator.geolocation.getCurrentPosition(function(position) {
                        const loc = {
                            lat: position.coords.latitude,
                            lng: position.coords.longitude
                        };
            
                        // Call checkNearbyEvent and wait for it to complete
                        Promise.resolve(Promo.checkNearbyEvent(loc))
                            .then(() => {
                                // Schedule the next check after 5 seconds once checkNearbyEvent completes
                                setTimeout(checkAndRepeat, 5000);
                            })
                            .catch(error => {
                                console.error("Error in checkNearbyEvent:", error);
                                // Retry after 5 seconds in case of an error
                                setTimeout(checkAndRepeat, 5000);
                            });
                    }, function(error) {
                        console.error("Error fetching location:", error);
                        // Retry after 5 seconds if geolocation fails
                        setTimeout(checkAndRepeat, 5000);
                    });
                }
            
                // Start the first check
                checkAndRepeat();
            }
            
            // Start the nearby event checking process
            startCheckingNearbyEvents();
            setTimeout(() => {
                sharedState.geolocateControl.trigger();
            }, 100)
            // check navigation and update nav isntructions
            navigator.geolocation.watchPosition(
                (position) => {
                    const userPos = {
                        lng: position.coords.longitude,
                        lat: position.coords.latitude,
                    };
                    if (sharedState.isUserRunning) {
                        Nav.updateNavigationInstructions(userPos);
                    }
                },
                (error) => {
                    console.error("Error retrieving geolocation:", error);
                },
                {
                    enableHighAccuracy: true,
                    maximumAge: 1000,       // Use cached position for up to 1 second
                    timeout: 5000           // Wait up to 5 seconds for a location fix
                }
            );
            sharedState.geolocateControl.on('trackuserlocationstart', ({target}) => {
                target.options.geolocation.getCurrentPosition((position) => {
                    Setup.setUserLocationMark([position.coords.longitude, position.coords.latitude]);
                    sharedState.userLocation = {
                        lng: position.coords.longitude,
                        lat: position.coords.latitude,
                        userHeading: position.coords.heading,
                    };
                })
                sharedState.userTouch = false
                if(!sharedState.userLocation) return
                sharedState.map.easeTo({
                    center: [sharedState.userLocation.lng, sharedState.userLocation.lat],
                    bearing: sharedState.userLocation.userHeading,  // Set the map's bearing to the user's heading
                    zoom: sharedState.isUserRunning ? 20 : 13,     // Keep the current zoom level
                    duration: 500         // Animation duration (optional)
                });
            }); 
            const compassButton = document.querySelector('.mapboxgl-ctrl-compass')
            if (compassButton) {
                compassButton.addEventListener('click', function(e) {
                    sharedState.userTouch  = true
                    e.preventDefault();
                });
            }
        });
        sharedState.hiddenMap.on('load', function () {
            const geoloHidl = new mapboxgl.GeolocateControl({ ...geolocationCogif });
            sharedState.hiddenMap.addControl(geoloHidl);
            setTimeout(() => {
                geoloHidl.trigger();
            }, 500)
        });
        sharedState.map.on('dragstart', () => {
            sharedState.userTouch  = true
            sharedState.switchoverState = 'POSINIT'
            const img = dingwenndId.getElementsByTagName('img')[0]
            img.setAttribute('src', `static/icons/posinit.svg`);
        });
        sharedState.map.on('dragend', () => {
            // if (switchoverState === 'POSINIT' && !isUserRunning) {
            //     map.setPitch(0, {duration: 500});
            //     map.setZoom(14);
            // }
        });
    })
    .catch(error => {
        console.error('Error fetching the access token:', error);
    });

document.addEventListener('click', function (e) {
    if (e.target.classList.contains('location-link')) {
        e.preventDefault();
        const markerId = e.target.getAttribute('data-marker-id');
        Setup.showMapTab();
        pauseAndpaly.style.display = 'none';
        document.getElementById('popupModal').style.display = 'none';

        Object.keys(window.mapMarkers).forEach(item => {
            if (window.mapMarkers[item].getPopup().isOpen()) {
                window.mapMarkers[item].togglePopup();
            }
        });

        const marker = window.mapMarkers[markerId];
        if (marker) {
            const markerCoordinates = marker.getLngLat();
            console.log(sharedState);
            sharedState.map.flyTo({
                center: markerCoordinates,
                zoom: 15,
                essential: true
            });
            if (!marker.getPopup().isOpen()) {
                marker.togglePopup();
            }
        } else {
            if (e.target.innerText) {
                getPlaceCoordWithName(e.target.innerText);
            }
            console.error('Marker with ID ' + markerId + ' not found.');
        }
    }
});

function openModal() {
    document.getElementById('form-modal').style.display = 'block';
}
  
function closeModal() {
    document.getElementById('form-modal').style.display = 'none';
}

// Optional: close modal on outside click
window.onclick = function(event) {
    const modal = document.getElementById('form-modal');
    if (event.target === modal) {
    modal.style.display = "none";
    }
};
window.openModal = openModal;
window.closeModal = closeModal;
