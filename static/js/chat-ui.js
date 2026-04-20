let currentChannel = "general";
let localMessageCount = 0;
const currentUser = localStorage.getItem("chatUser") || "me";

async function apiJson(url, options = {}) {
    const response = await fetch(url, options);

    if (response.status === 401) {
        window.location.href = "/login.html";
        throw new Error("Unauthorized");
    }

    if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Request failed: ${response.status}`);
    }

    return response.json();
}

async function loadChannels() {
    try {
        const payload = { user: currentUser };
        const data = await apiJson("/api/my-channels", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const channels = data.channels || [];
        const list = document.getElementById("channel-list");
        list.replaceChildren();

        channels.forEach((channel) => {
            const li = document.createElement("li");
            li.textContent = "# " + channel;
            li.onclick = () => selectChannel(channel);
            list.appendChild(li);
        });

        if (channels.length > 0) {
            selectChannel(channels[0]);
        }
    } catch (error) {
        console.error("loadChannels failed", error);
    }
}

function selectChannel(channel) {
    currentChannel = channel;
    document.getElementById("current-channel").textContent = "# " + channel;
    localMessageCount = 0;
    pollMessages();
}

async function pollMessages() {
    try {
        const messages = await apiJson("/api/get-messages", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ channel: currentChannel })
        });

        if (messages.length >= localMessageCount) {
            localMessageCount = messages.length;
            renderMessages(messages);
        }
    } catch (error) {
        console.error("pollMessages failed", error);
    }
}

function renderMessages(messages) {
    const container = document.getElementById("messages");
    container.replaceChildren();

    messages.forEach((message) => {
        const div = document.createElement("div");
        div.className = "msg";

        const timeSpan = document.createElement("span");
        timeSpan.className = "msg-time";
        timeSpan.textContent = `[${message.timestamp}]`;

        const senderSpan = document.createElement("span");
        senderSpan.className = "msg-sender";
        senderSpan.textContent = `${message.sender}:`;

        div.appendChild(timeSpan);
        div.appendChild(document.createTextNode(" "));
        div.appendChild(senderSpan);
        div.appendChild(document.createTextNode(" "));
        div.appendChild(document.createTextNode(message.message));

        container.appendChild(div);
    });

    container.scrollTop = container.scrollHeight;
}

async function sendMessage() {
    const input = document.getElementById("msg-input");
    const message = input.value.trim();
    if (!message) {
        return;
    }

    try {
        await apiJson("/api/send-channel", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                channel: currentChannel,
                message,
                sender: currentUser
            })
        });

        input.value = "";
        pollMessages();
    } catch (error) {
        console.error("sendMessage failed", error);
    }
}

async function createChannel() {
    const input = document.getElementById("channel-input");
    const channel = input.value.trim();
    if (!channel) {
        return;
    }

    try {
        await apiJson("/api/create-channel", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ channel, user: currentUser })
        });

        input.value = "";
        await loadChannels();
        selectChannel(channel);
    } catch (error) {
        console.error("createChannel failed", error);
    }
}

async function joinChannel() {
    const input = document.getElementById("channel-input");
    const channel = input.value.trim();
    if (!channel) {
        return;
    }

    try {
        await apiJson("/api/join-channel", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ channel, user: currentUser })
        });

        input.value = "";
        await loadChannels();
        selectChannel(channel);
    } catch (error) {
        console.error("joinChannel failed", error);
    }
}

window.onload = () => {
    loadChannels();
    setInterval(pollMessages, 2000);
};
