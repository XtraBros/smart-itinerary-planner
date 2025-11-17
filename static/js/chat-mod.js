import { sharedState } from "./main.js";
import { get_coordinates_without_route, addMarkers } from "./map-setup.js";

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

export async function postMessage(message, chatMessages) {
    // 1️⃣ Show user message
    appendMessage({ text: message, className: 'visitor-message', chatMessages });

    // 2️⃣ Show AI loading indicator
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

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // Split by newline for JSON chunks
            const lines = buffer.split('\n');
            buffer = lines.pop(); // incomplete line stays in buffer

            for (let line of lines) {
                if (!line.trim()) continue;
                let data;
                try {
                    data = JSON.parse(line);
                } catch (err) {
                    console.error('Invalid JSON chunk', line);
                    continue;
                }

                // Handle different chunk types
                switch (data.type) {
                    case 'content':
                        // Streaming: append to AI bubble
                        appendMessage({ text: data.content, chatMessages, isStreaming: true });
                        break;

                    case 'poi_data':
                        // Collect POI data for later
                        poiData = data.content;
                        break;

                    case 'done':
                        // Finished: optionally handle final task type or cleanup
                        console.log('Streaming done', data);
                        break;

                    case 'error':
                        appendMessage({ text: "Error: " + data.error, chatMessages, className: 'error-message' });
                        break;
                }
            }
        }

        // Process leftover buffer
        if (buffer.trim()) {
            try {
                const data = JSON.parse(buffer);
                if (data.type === 'content') appendMessage({ text: data.content, chatMessages, isStreaming: true });
            } catch { /* ignore */ }
        }

        // Once done, handle POI markers if any
        if (poiData.length > 0) {
            const placeNames = poiData.map(poi => poi.name);
            const coordinates = poiData.map(poi => [poi.longitude, poi.latitude]);
            addMarkers(placeNames, coordinates);
            sharedState.latestPOIs = poiData;
        }

    } catch (error) {
        console.error('Streaming error:', error.message || error);
        appendMessage({ text: "Error: " + error.message, chatMessages, className: 'error-message' });
    }
}


// creaate template and styles for each visitor/guide message.
export function appendMessage({ text, className, chatMessages, type, suggestion, placeNames, longAndlat, fromUser, isStreaming = false }) {
    let long = '';
    if (longAndlat && Array.isArray(longAndlat) && longAndlat.length && Array.isArray(longAndlat[0])) {
        long = longAndlat[0].join(',');
    }

    const currClass = className || 'guide-message';

    // --- Visitor message: leave as is ---
    if (className) {
        chatMessages.innerHTML += `<div class='chat-message ${currClass}'>${marked.parse(text)}</div>`;
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return;
    }

    // --- AI message ---
    // If text is null/empty, show loading indicator
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
        </div>`;
        return;
    } else {
        const bloaDox = document.getElementById("loading");
        if (bloaDox) bloaDox.remove();
    }

    // --- Determine if this is a special POI message ---
    if ((type === 'navigation' || type === 'introduction') && !(placeNames && placeNames.length > 1)) {
        chatMessages.innerHTML += `<div class='chat-message ${currClass}'>
            <div class='guideImage'><img src="static/icons/choml.png" alt="" srcset=""></div>
            <div class='guideText'>
                <div class='messageStype' id='streaming-message'>
                    ${text}
                    <p style='margin-top: 10px;'>
                        <button id="takeThereBut" onclick="Nav.navFunc(event, '${suggestion}', '${placeNames ? placeNames[0] : ''}', '${long}', '${fromUser}')">
                            <img src="static/icons/daohang.svg" alt="" srcset="">
                            <span>Take me there</span>
                        </button>
                    </p>
                </div>
            </div>
        </div>`;
    } else {
        // --- Normal AI message with streaming support ---
        // If streaming, append new text instead of replacing it
        if (isStreaming) {
            let streamingDiv = document.getElementById('streaming-message');
            if (!streamingDiv) {
                // First chunk: create container
                chatMessages.innerHTML += `<div class='chat-message ${currClass}'>
                    <div class='guideImage'><img src="static/icons/choml.png" alt="" srcset=""></div>
                    <div class='guideText'>
                        <div class='messageStype' id='streaming-message'>${text}</div>
                    </div>
                </div>`;
            } else {
                // Subsequent chunks: append
                streamingDiv.innerHTML += text;
            }
        } else {
            // Normal full AI message
            chatMessages.innerHTML += `<div class='chat-message ${currClass}'>
                <div class='guideImage'><img src="static/icons/choml.png" alt="" srcset=""></div>
                <div class='guideText'>
                    <div class='messageStype'>
                        ${text}
                    </div>
                </div>
            </div>`;
        }
    }

    chatMessages.scrollTop = chatMessages.scrollHeight;
}
