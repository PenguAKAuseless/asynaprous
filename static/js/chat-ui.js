let currentChannel = "general";
let localMessageCount = 0;

async function loadChannels() {
    try {
        const res = await fetch("/api/channels");
        if (res.status === 401) {
            window.location.href = "/login.html";
            return;
        }
        if (!res.ok) {
            throw new Error("Unable to load channels");
        }

        const channels = await res.json();
        const list = document.getElementById("channel-list");
        list.replaceChildren();

        channels.forEach(c => {
        let li = document.createElement("li");
        li.textContent = "# " + c;
        li.onclick = () => selectChannel(c);
        list.appendChild(li);
        });

        if (channels.length > 0) {
            selectChannel(channels[0]);
        }
    } catch (error) {
        console.error("loadChannels failed", error);
    }
}
/*----example
    channels is an array like ["general", "networking"].
    loops - forEach() - first loop: c = "general" 
    createElement("li") - creates a new <li> element - thẻ HTML empty - save in variable li
    # + c - context inside <li> is # general --> <li># general</li>
    onClick - when user click on <li>, do selectChannel("general") - wait until user click (meaning of () => )
    append <li> to <ul>
*/ 

function selectChannel(channel) {
    // No need - just update value, change content, reset counter, poll messages
    currentChannel = channel;
    document.getElementById("current-channel").textContent = "# " + channel;
    localMessageCount = 0; // Reset counter for the new channel
    pollMessages();
}
/*
    switch the value of currentChannel to the new channel --> sync
    reset counter because of new channel
    polling messages for the new channel - fetch messages from BE and render to UI

*/

async function pollMessages() {
    try {
        const res = await fetch("/api/get-messages", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ channel: currentChannel })
        });

        if (res.status === 401) {
            window.location.href = "/login.html";
            return;
        }

        if (!res.ok) {
            throw new Error("Unable to poll messages");
        }

        const messages = await res.json();

        if (messages.length > localMessageCount) {
            if (localMessageCount !== 0) {
                console.log("New message notification triggered!");
            }
            localMessageCount = messages.length;
            renderMessages(messages);
        }
    } catch (error) {
        console.error("pollMessages failed", error);
    }
}
/*
    fetch messages send to endpoint /api/get-messages
    BE send back an array of messages for the current channel
    if length > local, have new messages - update local count and render to UI
    but !==0 : just noti new message - avoid old noti when load channel
    update local count
    render messages to UI - update the message list in the UI

*/

function renderMessages(messages) {
    const container = document.getElementById("messages");
    container.replaceChildren();
    messages.forEach(m => {
        let div = document.createElement("div");
        div.className = "msg";

        let timeSpan = document.createElement("span");
        timeSpan.className = "msg-time";
        timeSpan.textContent = `[${m.timestamp}]`;

        let senderSpan = document.createElement("span");
        senderSpan.className = "msg-sender";
        senderSpan.textContent = `${m.sender}:`;

        div.appendChild(timeSpan);
        div.appendChild(document.createTextNode(" "));
        div.appendChild(senderSpan);
        div.appendChild(document.createTextNode(" "));
        div.appendChild(document.createTextNode(m.message));

        container.appendChild(div);
    });
    container.scrollTop = container.scrollHeight;
}
/*
    find id of message which is ready to show
    remove all old message container - replaceChildren() 
    loop: create timestamp span, sender span, append to message div, append message div to container
    scroll to bottom - always show the latest message
*/

async function sendMessage() {
    const input = document.getElementById("msg-input");
    const msg = input.value.trim();
    if (!msg) return;

    try {
        const res = await fetch("/api/send-channel", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ channel: currentChannel, message: msg, sender: "me" })
        });

        if (res.status === 401) {
            window.location.href = "/login.html";
            return;
        }

        if (!res.ok) {
            throw new Error("Unable to send message");
        }

        input.value = "";
        pollMessages();
    } catch (error) {
        console.error("sendMessage failed", error);
    }
}
/*
    find textbox element, get message, trim whitespace, if empty return
    wait until fetch to send message to BE (endpoint /api/send-channel)
    reset input box
    immediately poll messages to update UI with the new message

*/
// Short polling every 2 seconds to check BE new messages - Notification system
window.onload = () => {
    loadChannels();
    setInterval(pollMessages, 2000);
};