const mapEl = document.getElementById('map')
const poiList = document.getElementById('poiList')
const tabMap = document.getElementById('tabMap')
const tabList = document.getElementById('tabList')
const poiSwiper = document.getElementById('poiSwiper');
const startNav = document.getElementById('startNav');
const totMinus = document.getElementById('totMinus');
const totDist = document.getElementById('totDist');
const navcompleted = document.getElementById('navcompleted');
const dingwenndId = document.getElementById('dingwennd');
let simulationTimeout;         // Variable to store the timeout ID
let simulatePoint;

import { thumbnailURI, sharedState} from "./main.js";
import { optimizeRoute, isUserOffRoute, disableNavigationMode, closedNavfun } from "./nav-mod.js";

export function initProperty() {
    sharedState.routeIndex = 0;
    sharedState.currentStepIndex = 0;
    sharedState.walkedRoute = []
    simulatePoint = null
    clearTimeout(simulationTimeout);
}
export function setUserLocationMark(coord) {
    console.log("Setting User Marker.")
    if (sharedState.userMarker) {
        sharedState.userMarker.remove()
        sharedState.userMarker = null
    }
    const el = document.createElement('div');
    el.insertAdjacentHTML('beforeend', `<div class='user-location-marker'></div>`);
    sharedState.userMarker = new mapboxgl.Marker({
        // rotationAlignment: 'map',
        element: el
    })
        .setLngLat(coord)
        .addTo(sharedState.map);
}
// User location
export function getUserCurrentPosition(callBack, error) {
    navigator.geolocation.getCurrentPosition((position) => {
        sharedState.userLocation = {
            lng: position.coords.longitude,
            lat: position.coords.latitude,
            userHeading: position.coords.heading,
        };
        setUserLocationMark([position.coords.longitude, position.coords.latitude]);
        if (callBack) {
            callBack(sharedState.userLocation)
        }
        // get POIs
        getPoisByLocation(sharedState.userLocation);
        console.log(`User location updated to: ${sharedState.userLocation.lat}, ${sharedState.userLocation.lng}`);
    }, (e) => {
        if (error) {
            cuerror(e)
        }
        console.error('Error obtaining geolocation:', e);
    });
}

export async function getPoisByLocation(location) {
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
        // Fetch distances and times from the new endpoint
        const distancesResponse = await fetch('/calculate_distances', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ place_names: poisData, user_location: userLocation }),
        });
        const distancesData = await distancesResponse.json();

        fetchTemplate('static/html/info-card.html').then(template => {
            const parser = new DOMParser();
            let contenxt = '';
            let listCont = '';
            poisData.forEach((placeName, index) => {
                // Construct the Google Cloud thumbnail URL
                var formattedPlaceName = placeName.toLowerCase().replace(/\s+/g, '-');
                // Check if placeName contains "station" or "toilet" and update accordingly
                if (placeName.toLowerCase().includes("toilet")) {
                    formattedPlaceName = "toilet";
                } else if (placeName.toLowerCase().includes("station")) {
                    formattedPlaceName = "station";
                }
                // Skip adding markers for toilets and stations
                if (formattedPlaceName === "toilet" || formattedPlaceName === "station") {
                    return;  // Continue to the next POI without adding a marker
                }
                const thumbnailUrl = placeInfoResponse[placeName] ? `${thumbnailURI}${formattedPlaceName}.jpg` : '/static/icons/default.png';
                // Get distance and time from distancesData
                const distance = distancesData[placeName]?.distance ?? 'N/A'; // Use nullish coalescing operator
                const time = distancesData[placeName]?.time !== undefined 
                    ? `${Math.round(distancesData[placeName].time)} mins` 
                    : 'N/A';
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
                                                ${distance}m
                                            </span>
                                            <span>
                                                <img src="static/icons/time.svg" alt="" srcset="">
                                                ${time}
                                            </span>
                                        </p>
                                    </div>
                                </div>
                            </div>`;
    
                listCont += setMapList({index, thumbnailUrl, placeName});
                // orderOfVisit[0].map((item, i) => {
                //     if (item === placeName) {
                //         addMarkertoMap({ placeName, category: 'dinwei', index, template, description: '', parser, location: orderOfVisit[1][i] })
                //         return orderOfVisit[1][i]
                //     }
                // })
            });
            swiperconent.innerHTML = contenxt;
            poiList.innerHTML = listCont;
        });
    } catch (error) {
        console.error('Get Pois by Location', error);
        return null;
    }
}

export function setMapList({index, placeName, thumbnailUrl}) {
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

let firstTime = null;

export function handleOrientationChange(event) {
    // console.log("User facing direction changed.")
    const mapUserLocation = document.getElementsByClassName('mapboxgl-user-location')[0] 
    const holdMapUser = document.getElementsByClassName('mapboxgl-user-location')[1]
    if (sharedState.map && event.alpha !== null && sharedState.switchoverState === 'FOCUS') {
        if (sharedState.firstClick) {
            if (!firstTime) {
                firstTime = setTimeout(() => {
                    clearTimeout(firstTime);
                    firstTime = null
                    sharedState.firstClick = false
                }, 600)
            }
        } else {
            if (holdMapUser && mapUserLocation) {
                const angle = normalizeAngle(getRotateZ(holdMapUser.style.transform));
                // document.getElementsByClassName('newHeader')[0].innerText = `${getRotateZ(holdMapUser.style.transform)} : ${angle}`
                sharedState.map.rotateTo(angle, { animate: false });
            }
        }
    }
    
    if (sharedState.userMarker && mapUserLocation) {
        const markerElement = sharedState.userMarker.getElement().getElementsByClassName('user-location-marker')[0]
        markerElement.style.transform = `rotateZ(${getRotateZ(mapUserLocation.style.transform)}deg)`
    
    }
}

export function detectDevice() {
    const userAgent = navigator.userAgent || navigator.vendor || window.opera;
    const isIOS = /iPad|iPhone|iPod/.test(userAgent) || 
                  (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    if (isIOS) {
        return 'iOS';
    }
    if (/android/i.test(userAgent)) {
        return 'Android';
    }
    return 'Unknown';
}

export function debounce(fn, delay) {
    let timer;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delay);
    };
}

export function domeShowBootFuc() {
    foodBox.classList.add('fadeshowin');
    // getSuggestion(1);
}

export async function getPlaceCoordWithName(place, isNotMarker) {
    if (!isNotMarker) {
        disableNavigationMode();
        closedNavfun();
        if (sharedState.map.getSource('route')) {
            sharedState.map.removeLayer('route');
            sharedState.map.removeSource('route');
            if (sharedState.map.getLayer('directions')) {
                sharedState.map.removeLayer('directions');
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
        sharedState.map.flyTo({
            center: waypoints[0],
            essential: true
        });
    }
    addMarkers([place], waypoints);
    return responseData
}

export function showMapTab() {
    mapEl.style.display = 'block';
    poiList.style.display = 'none';
    tabList.classList.remove('activeButton');
    tabMap.classList.add('activeButton');
}

export function navDitle(e, name) {
    getPlaceCoordWithName(name);
    showMapTab();
}

export function handerMap(e, type) {
    if (type === 'list') {
        tabMap.classList.remove('activeButton');
        mapEl.style.display = 'none'
        poiList.style.display = 'block'
    } else {
        tabList.classList.remove('activeButton');
        mapEl.style.display = 'block'
        poiList.style.display = 'none'
    }
    e.target.classList.add('activeButton')
    e.preventDefault();
}
export function switchoverHandled() {
    sharedState.userTouch = false
    sharedState.switchoverState = sharedState.switchoverState === 'POSINIT' ? 'FOCUS' : 'POSINIT'
    const img = dingwenndId.getElementsByTagName('img')[0]
    img.setAttribute('src', `static/icons/${sharedState.switchoverState === 'FOCUS' ? 'nios' : 'posinit'}.svg`);
    if (sharedState.isUserRunning) {
        if (sharedState.switchoverState === 'FOCUS') {
            sharedState.map.setCenter([sharedState.userLocation.lng, sharedState.userLocation.lat]);
        }
        return
    }
    if (sharedState.switchoverState === 'FOCUS') {
        sharedState.map.setZoom(17);
        sharedState.map.setPitch(60, {duration: 10});
        sharedState.map.setCenter([sharedState.userLocation.lng, sharedState.userLocation.lat]);
    } else {
        outFoucsMode()
    }
}

export function outFoucsMode() {
    sharedState.map.setZoom(14);
    sharedState.map.setPitch(0, {duration: 10});
    sharedState.map.resetNorth({duration: 10});
}

export function getRotateZ(transform) {
    if (!transform) return 0;
    const match = transform.match(/rotateZ\(([-0-9.]+)deg\)/);
    if (match) {
        return parseFloat(match[1]); // 返回角度值
    } else {
        return 0; // 如果没有 rotateZ，则返回 0
    }
}

export function userCalculate(start, end) {
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

export function paintLine(resRoute, isZoom = true) {
    showMapTab();
    let bers = 0;
    const startPrit = [sharedState.userLocation.lng, sharedState.userLocation.lat];
    let endProit = []
    if (resRoute && resRoute.coordinates && resRoute.coordinates.length) {
        endProit = resRoute.coordinates[resRoute.coordinates.length - 1]
        bers = userCalculate(resRoute.coordinates[0], endProit);
        setDottedLine()
    }
    if (!sharedState.map.getSource('previewRoute')) {
        sharedState.map.addSource('previewRoute', {
            'type': 'geojson',
            'data': {
                'type': 'Feature',
                'properties': {},
                'geometry': resRoute,
            }
        });
    } else {
        sharedState.map.getSource('previewRoute').setData({
            "type": "Feature",
            "geometry": resRoute,
        });
    }
    if (!sharedState.map.getLayer('prewroute')) {
        // 添加边框图层
        sharedState.map.addLayer({
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
        sharedState.map.addLayer({
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
    sharedState.map.fitBounds([startPrit, endProit], {
        // bearing: bers,
        padding: 50, // 距离屏幕边缘的内边距（以像素为单位）
        maxZoom: 16,
        duration: 1000
    });
}

export function setDottedLine() {
    if (sharedState.endPlaceProt && sharedState.walkStepsNavs && sharedState.walkStepsNavs.waypoints.length) {
        const userfirstDistance = sharedState.walkStepsNavs.waypoints[0].distance;
        const { distance, isInPolygon} = isUserOffRoute(sharedState.userLocation, sharedState.route);
        if (userfirstDistance > 5 && distance > 5 && !isInPolygon) {
            const geometry = {
                coordinates: [
                    [sharedState.userLocation.lng, sharedState.userLocation.lat],
                    sharedState.walkStepsNavs.waypoints[0].location
                ],
                type: "LineString",
            }
            if (!sharedState.map.getSource('dottedLine')) {
                sharedState.map.addSource('dottedLine', {
                    'type': 'geojson',
                    'data': {
                        'type': 'Feature',
                        'properties': {},
                        'geometry': geometry,
                    }
                });
            } else {
                sharedState.map.getSource('dottedLine').setData({
                    "type": "Feature",
                    "geometry": geometry,
                });
            }
            if (!sharedState.map.getLayer('dottedLineroute')) {
                sharedState.map.addLayer({
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
        } else if (sharedState.map.getLayer('dottedLineroute')) {
            sharedState.map.removeLayer('dottedLineroute');
        }
    }
}

export function displayRoute(placeNames, rawCoordinates, fromUser) {
    return new Promise((resolve, reject) => {
        // Clear existing routes
        if (sharedState.map.getSource('route')) {
            sharedState.map.removeLayer('route');
            sharedState.map.removeSource('route');
            if (sharedState.map.getLayer('directions')) {
                sharedState.map.removeLayer('directions');
            }
        }
        addMarkers(placeNames, rawCoordinates);
        sharedState.endPlaceProt = rawCoordinates;
        // Check number of waypoints. If less than 25, execute the usual. Else, fetch centroids.
        let allCoordinates;
        if (fromUser) {
            allCoordinates = [[sharedState.userLocation.lng, sharedState.userLocation.lat], ...rawCoordinates];
        } else {
            allCoordinates = rawCoordinates;
        }
        const coordinates = allCoordinates.map(coord => coord.join(',')).join(';');
        console.log("Coordinates to go to: " + coordinates, rawCoordinates)
        // Process fetched directions data or centroids
        getMapboxWalkRoute(coordinates)
            .then(result => {
                let centerPot = [sharedState.userLocation.lng, sharedState.userLocation.lat]
                if (result.legs && result.route) {
                    sharedState.geolocateControl.on('geolocate', (position) => {
                        const cuerrorUserLoc = {
                            lng: position.coords.longitude,
                            lat: position.coords.latitude,
                            userHeading: position.coords.heading,
                        };
                        sharedState.userLocation = cuerrorUserLoc
                        const { distance, nearestPointOnLine, isInPolygon  } = isUserOffRoute(cuerrorUserLoc, sharedState.route);
                        if (sharedState.userMarker) {
                            const CunrrPoint = distance > 10 ? [position.coords.longitude, position.coords.latitude] : nearestPointOnLine.geometry.coordinates
                            sharedState.userMarker.setLngLat(CunrrPoint)
                            if (!sharedState.userTouch && !sharedState.firstClick) {
                                sharedState.map.setCenter(CunrrPoint);
                            }
                        }
                        setDottedLine()
                        if ((distance > 20 || !isInPolygon) && sharedState.endPlaceProt) {
                            console.log('User is off-route, recalculating route...');
                            recalculateRoute(cuerrorUserLoc, sharedState.endPlaceProt);  // Call reroute function
                        }
                    });
                    // Extract route instructions
                    if (result.route.coordinates && result.route.coordinates.length) {
                        centerPot = result.route.coordinates[Math.floor(result.route.coordinates.length * 0.5)]
                    }
                } else if (result.newUrl) {
                    // Handle URL for later use case
                    resolve(result.newUrl);
                } else {
                    throw new Error('Invalid data received');
                }
                sharedState.map.flyTo({
                    center: centerPot,
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

export function getMapboxWalkRoute(coordinates) {
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
                // console.log('------data->>>>>>>>>', data)
                const totalDistance = legs[0].distance.toFixed(2);
                const totalDuration = legs[0].duration;
                if (totMinus && totDist) {
                    totMinus.innerText = `${Math.ceil(totalDuration / 60)}min`
                    totDist.innerText = totalDistance > 1000 ? `${(totalDistance / 1000).toFixed(2)}km` : `${totalDistance}m`
                }
                sharedState.route = data.routes[0].geometry;
                const result = data.routes[0].geometry;
                sharedState.steps = data.routes[0].legs[0].steps;
                sharedState.walkStepsNavs = data
                return { legs: legs, route: result };
            } else {
                console.error('No route found: ', data);
                throw new Error('No route found');
            }
        });
}

export function disminiNav() {
    startNav.classList.add('fadeshowin');
    poiSwiper.classList.remove('fadeshowin');
    navcompleted.classList.remove('fadeshowin');
    navcompleted.classList.add('fadeout');
}

export async function getCoordinatesWithPlace(places) {
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

export async function get_coordinates(data, fromUser) {
    const orderOfVisit = await getCoordinatesWithPlace(data);
    return orderOfVisit;
}

export async function get_coordinates_without_route(data) {
    const orderOfVisit = await getCoordinatesWithPlace(data);
    return orderOfVisit;
}
function normalizeAngle(angle) {
    return (angle % 360 + 360) % 360;
}
export function addMarkers(placeNames, waypoints) {
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

export function displayByCategory(category, element) {
    if (window.mapMarkers) {
        for (const [key, value] of Object.entries(window.mapMarkers)) {
            value.remove();
        }
    }
    if (element.getAttribute('class').includes('active')) {
        element.classList.remove('active')
        return;
    }
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

export function addMarkertoMap({ placeName, category, index, template, description, parser, location }) {
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
        .addTo(sharedState.map);
    // Store marker by ID
    window.mapMarkers[popupId] = marker;
    return setMapList({index, thumbnailUrl: place.thumbnail, placeName});
}

export function fetchTemplate(url) {
    return fetch(url).then(response => response.text());
}

export function populateTemplate(template, data) {
    return template.replace(/{{(\w+)}}/g, (match, key) => data[key] || '');
}
// function to get places data.
export function fetchPlacesData(places) {
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
export function attachEventListenersToHyperlinks() {
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
                window.sharedState.map.flyTo({
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

export function awaitGetPlaceCoordWithName(place) {
    // Return a promise that resolves when the getPlaceCoordWithName function completes
    return new Promise((resolve, reject) => {
        getPlaceCoordWithName(place, true)
            .then((res) => resolve(res)) // Resolve the promise when getPlaceCoordWithName completes
            .catch(error => reject(error)); // Reject the promise if there’s an error
    });
}

// Suggestion Button:
// EXAMPLE usage of endpoint:
// async function getSuggestion(type) {
//     if (!chatMessages) {
//         var chatMessages = document.getElementById("chatbot-messages");
//     }
//     try {
//         // Send a POST request to the /suggestion endpoint
//         const response = await fetch('/suggestion', {
//             method: 'POST',
//             headers: {
//                 'Content-Type': 'application/json'
//             },
//             body: JSON.stringify({ choice: type })
//         });

//         // Check if the response is OK (status code 200-299)
//         if (!response.ok) {
//             throw new Error(`HTTP error! status: ${response.status}`);
//         }

//         // Parse the JSON response
//         const data = await response.json();
//         // Check response in console:
//         console.log('Response from /suggestion: ', data);
//         // Get info of poi and make marker
//         suggestionData = await awaitGetPlaceCoordWithName(data.POI);
//         //Post the message in chatbox:
//         appendMessage({
//             text: data.message,
//             chatMessages,
//             type: 'location',
//             suggestion: 'suggestion',
//         });
//         attachEventListenersToHyperlinks();
//     } catch (error) {
//         console.error('Error fetching suggestion:', error);
//     }
// }