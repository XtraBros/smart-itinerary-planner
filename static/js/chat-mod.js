import { sharedState } from "./main.js";
import { addMarkers, disminiNav, displayRoute } from "./map-setup.js"

export function systemQuestionFunc(e) {
    const chatMessages = document.getElementById("chatbot-messages");
    postMessage(e.target.innerText, chatMessages);
}
window.systemQuestionFunc = systemQuestionFunc;

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
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }
}
window.submitChat = function(event) {
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
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }
}

// Post message to server and handle streaming response
export async function postMessage(message, chatMessages) {
    appendMessage({ text: message, className: 'visitor-message', chatMessages });
    appendMessage({ text: null, chatMessages });

    try {
        const response = await fetch('/ops_router', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message, user_location: sharedState.userLocation })
        });

        if (!response.ok) throw new Error('Network response was not ok ' + response.statusText);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let poiData = [];
        let currentStreamingId = null;
        let currentSuggestion = '';
        let currentPlaceNames = [];
        let currentLongAndLat = [];
        let currentFromUser = '1';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (let line of lines) {
                if (!line.trim()) continue;
                let data;
                try { data = JSON.parse(line); }
                catch { console.error('Invalid JSON chunk', line); continue; }

                switch (data.type) {
                    case 'content':
                        if (!currentStreamingId) {
                            currentStreamingId = 'streaming-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
                        }

                        if (data.placeNames) currentPlaceNames = data.placeNames;
                        if (data.longAndlat) currentLongAndLat = data.longAndlat;
                        if (data.suggestion) currentSuggestion = data.suggestion;
                        if (data.fromUser) currentFromUser = data.fromUser;

                        appendMessage({
                            text: data.content,
                            chatMessages,
                            isStreaming: true,
                            streamingId: currentStreamingId
                        });
                        break;

                    case 'poi_data':
                        poiData = data.content;
                        break;

                    case 'done':
                        console.log('--- DONE chunk received ---');
                        console.log('task:', data.task);
                        console.log('currentStreamingId:', currentStreamingId);
                        console.log('currentSuggestion:', currentSuggestion);
                        console.log('currentPlaceNames:', currentPlaceNames);
                        console.log('currentLongAndLat:', currentLongAndLat);
                        console.log('currentFromUser:', currentFromUser);
                    
                        // Get container of last streaming message
                        const container = document.getElementById(currentStreamingId);
                        console.log('container element:', container);
                    
                        // Only attach POI button for introduction or navigation tasks
                        if (container && (data.task === 'navigation' || data.task === 'introduction')) {
                            console.log('Attaching POI button...');
                            attachPOIButton({
                                container,
                                suggestion: data.suggestion || '',
                                placeNames: data.placeNames || [],
                                longAndlat: data.longAndlat || [],
                                fromUser: data.fromUser || '1'
                            });
                        } else {
                            console.log('POI button not attached (container missing or task not eligible)');
                        }
                        // Reset for next message
                        currentStreamingId = null;
                        currentSuggestion = '';
                        currentPlaceNames = [];
                        currentLongAndLat = [];
                        currentFromUser = '1';
                        break;
                    
                    case 'error':
                        console.log({ text: "Error: " + data.error, chatMessages, className: 'error-message' });
                        break;
                }
            }
        }

        if (buffer.trim()) {
            try {
                const data = JSON.parse(buffer);
                if (data.type === 'content') appendMessage({ text: data.content, chatMessages, isStreaming: true });
            } catch {}
        }

        if (poiData.length > 0) {
            const placeNames = poiData.map(poi => poi.name);
            const coordinates = poiData.map(poi => [poi.longitude, poi.latitude]);
            addMarkers(placeNames, coordinates);
            sharedState.latestPOIs = poiData;
        }

    } catch (error) {
        console.error('Streaming error:', error.message || error);
        console.log({ text: "Error: " + error.message, chatMessages, className: 'error-message' });
    }
}


// Append message to chat
export function appendMessage({ 
    text, className, chatMessages, isStreaming = false, streamingId = null 
}) {
    const currClass = className || 'guide-message';

    // Visitor messages
    if (className) {
        chatMessages.innerHTML += `<div class='chat-message ${currClass}'>${marked.parse(text)}</div>`;
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return;
    }

    // Loading indicator
    if (text === null) {
        chatMessages.innerHTML += `<div id='loading' class='chat-message ${currClass}'>
            <div class='guideImage'><img src="static/icons/choml.png" alt=""></div>
            <div class='guideText'>
                <div class='messageStype'>
                    <div class="dots"><div></div><div></div><div></div></div>
                </div>
            </div>
        </div>`;
        return;
    } else {
        const bloaDox = document.getElementById("loading");
        if (bloaDox) bloaDox.remove();
    }

    // Streaming messages
    const divId = streamingId || ('streaming-' + Date.now() + '-' + Math.floor(Math.random() * 1000));
    let streamingDiv = document.getElementById(divId);

    if (isStreaming) {
        if (!streamingDiv) {
            chatMessages.innerHTML += `<div class='chat-message ${currClass}'>
                <div class='guideImage'><img src="static/icons/choml.png" alt=""></div>
                <div class='guideText'>
                    <div class='messageStype' id='${divId}'>${text}</div>
                </div>
            </div>`;
            streamingDiv = document.getElementById(divId);
        } else {
            streamingDiv.innerHTML += text;
        }
    } else {
        chatMessages.innerHTML += `<div class='chat-message ${currClass}'>
            <div class='guideImage'><img src="static/icons/choml.png" alt=""></div>
            <div class='guideText'>
                <div class='messageStype'>${text}</div>
            </div>
        </div>`;
    }

    chatMessages.scrollTop = chatMessages.scrollHeight;
}

export function attachPOIButton({ container, placeNames = [], longAndlat = [], fromUser = '1' }) {
    if (!container || !placeNames || placeNames.length === 0 || !longAndlat || longAndlat.length === 0) return;

    const coordStr = Array.isArray(longAndlat[0]) ? longAndlat[0].join(',') : longAndlat.join(',');
    const buttonWrapper = document.createElement('p');
    buttonWrapper.style.marginTop = '10px';

    const button = document.createElement('button');
    button.id = 'takeThereBut';

    // Assign click function directly
    button.onclick = async function (e) {
        e.preventDefault();
        
        disminiNav();
        const [lonStr, latStr] = coordStr.split(',');
        const lon = parseFloat(lonStr);
        const lat = parseFloat(latStr);
        const popupModal = document.getElementById('popupModal');

        let waypoints = [];
        if (sharedState.userLocation && sharedState.userLocation.length === 2) {
            // From user location to POI
            waypoints = [
                sharedState.userLocation,
                [lon, lat]
            ];
        } else {
            waypoints = [[lon, lat]];
        }
        popupModal.style.display = "none";
        await displayRoute(placeNames, waypoints, fromUser === '1');

    };

    const img = document.createElement('img');
    img.src = 'static/icons/daohang.svg';
    img.alt = '';

    const span = document.createElement('span');
    span.textContent = 'Take me there';

    button.appendChild(img);
    button.appendChild(span);
    buttonWrapper.appendChild(button);
    container.appendChild(buttonWrapper);
}
