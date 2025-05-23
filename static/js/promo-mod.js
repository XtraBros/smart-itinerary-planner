const blacklist = new Set();
import { fetchPlacesData } from "./map-setup.js";
import { appendMessage } from "./chat-mod.js";

export async function checkNearbyEvent(location) {
    // console.log("Checking nearby events.")
    try {
        const response = await fetch('/find_nearby_pois', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ user_location: { longitude: location.lng, latitude: location.lat }, radius_in_meters: 30 })
        });

        if (!response.ok) {
            throw new Error('Network response was not ok');
        }

        const poisData = await response.json();
        const placeInfoResponse = await fetchPlacesData(poisData);
        if (poisData && !poisData.length) return
        // prompt suggestion if not recent:
        const placeNames = [];
        const coordinates = [];

        Object.keys(placeInfoResponse).forEach(placeName => {
            if (!blacklist.has(placeName)) { // Check if placeName is not in the blacklist
                placeNames.push(placeName);
                coordinates.push(placeInfoResponse[placeName].location);
            }
        });
        if (placeNames.length > 0) {

            let nextResponse = await fetch('/check_events', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ places: placeNames, coordinates: coordinates, blacklist: blacklist })
            });
            placeNames.forEach(placeName => {
                blacklist.add(placeName);
            });
            console.log("== blacklist == " + Array.from(blacklist));
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
        }
    } catch (error) {
        console.error('Get Pois by Location', error);
        return null;
    }
}

// // Prompt message after inactivity
// function resetTimer() {
//     // Clear any existing timer
//     if (suggestionTimer) {
//         console.log("Resetting suggstion timer.")
//         clearTimeout(suggestionTimer);
//     }
//     console.log("Starting a timer for suggestions.")
//     // Set a new timer that runs after 5 minutes
//     suggestionTimer = setTimeout(() => {
//         console.log("5 minutes since last message, prompting suggestions.")
//         // getSuggestion(3);  // Trigger suggestion after 5 minutes of inactivity
//         // getSuggestion(4);  // recommend another food.beverage option for 2nd demo.
//         clearTimeout(suggestionTimer);  // Stop the timer after suggestion is made
//         suggestionTimer = null;  // Set timer to null, so it can be started again
//     }, suggestionTimeout);
// }