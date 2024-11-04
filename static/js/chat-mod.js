import { sharedState } from "./main.js";
import { get_coordinates_without_route, addMarkers, attachEventListenersToHyperlinks } from "./map-setup.js";

export function systemQuestionFunc(e) {
    const chatMessages = document.getElementById("chatbot-messages");
    postMessage(e.target.innerText, chatMessages);
}

export function submitChat(event) {
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

export async function postMessage(message, chatMessages) {
    appendMessage({ text: message, className: 'visitor-message', chatMessages });
    appendMessage({ text: null, chatMessages });
    try {
        // Send message to Flask endpoint and get the response
        let response = await fetch('/ask_plan', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: message, userLocation: sharedState.userLocation })
        });
        if (!response.ok) {
            throw new Error('Network response was not ok ' + response.statusText);
        }
        let data = await response.json();
        console.log("GPT response: " + JSON.stringify(data));
        // check for operation type and run route functions if neccesarry.
        if (data.operation == "location") {
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
        } else {
            appendMessage({ text: data.response, chatMessages });
        }
    } catch (error) {
        console.error('Error:', error.message || error);
    }
}
// creaate template and styles for each visitor/guide message.
export function appendMessage({ text, className, chatMessages, type, suggestion, placeNames, longAndlat, fromUser }) {
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
                        <button id="takeThereBut" onclick="Nav.navFunc(event, '${suggestion}', '${placeNames ? placeNames[0] : ''}', '${long}', '${fromUser}')">
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