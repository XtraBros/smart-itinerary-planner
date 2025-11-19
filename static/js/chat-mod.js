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

// Post message to server and handle streaming response
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
        let currentStreamingId = null;

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
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

                switch (data.type) {
                    case 'content':
                        if (!currentStreamingId) {
                            // generate a unique ID for this streaming message
                            currentStreamingId = 'streaming-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
                        }
                        appendMessage({
                            text: data.content,
                            chatMessages,
                            isStreaming: true,
                            type: data.task,
                            streamingId: currentStreamingId
                        });
                        break;

                    case 'poi_data':
                        poiData = data.content;
                        break;

                    case 'done':
                        if (currentStreamingId) {
                            appendMessage({
                                text: '', 
                                chatMessages,
                                isStreaming: true,
                                type: data.task,
                                streamComplete: true,
                                streamingId: currentStreamingId,
                                suggestion: data.suggestion,
                                placeNames: data.placeNames,
                                longAndlat: data.longAndlat,
                                fromUser: data.fromUser
                            });
                            currentStreamingId = null; // reset for next message
                        }
                        break;

                    case 'error':
                        console.log({ text: "Error: " + data.error, chatMessages, className: 'error-message' });
                        break;
                }
            }
        }

        // leftover buffer
        if (buffer.trim()) {
            try {
                const data = JSON.parse(buffer);
                if (data.type === 'content') appendMessage({ text: data.content, chatMessages, isStreaming: true });
            } catch { /* ignore */ }
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
export function appendMessage({ text, className, chatMessages, type, suggestion, placeNames, longAndlat, fromUser, isStreaming = false, streamComplete = false, streamingId = null }) {
    let long = '';
    if (longAndlat && Array.isArray(longAndlat) && longAndlat.length && Array.isArray(longAndlat[0])) {
        long = longAndlat[0].join(',');
    }

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

    const isSpecialPOI = (type === 'navigation' || type === 'introduction') && !(placeNames && placeNames.length > 1);

    // For streaming messages, use unique streamingId
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

        if (streamComplete && isSpecialPOI && streamingDiv) {
            streamingDiv.innerHTML += `<p style='margin-top: 10px;'>
                <button id="takeThereBut" onclick="Nav.navFunc(event, '${suggestion}', '${placeNames ? placeNames[0] : ''}', '${long}', '${fromUser}')">
                    <img src="static/icons/daohang.svg" alt="">
                    <span>Take me there</span>
                </button>
            </p>`;
        }

    } else {
        chatMessages.innerHTML += `<div class='chat-message ${currClass}'>
            <div class='guideImage'><img src="static/icons/choml.png" alt=""></div>
            <div class='guideText'>
                <div class='messageStype'>
                    ${text}
                    ${isSpecialPOI ? `<p style='margin-top: 10px;'>
                        <button id="takeThereBut" onclick="Nav.navFunc(event, '${suggestion}', '${placeNames ? placeNames[0] : ''}', '${long}', '${fromUser}')">
                            <img src="static/icons/daohang.svg" alt="">
                            <span>Take me there</span>
                        </button>
                    </p>` : ''}
                </div>
            </div>
        </div>`;
    }

    chatMessages.scrollTop = chatMessages.scrollHeight;
}
