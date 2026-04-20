let currentChannel = "";
let currentUser = "";
const messageCountByChannel = new Map();
let latestPollId = 0;

async function apiJson(url, options = {}) {
    const response = await fetch(url, {
        credentials: "same-origin",
        ...options
    });

    if (response.status === 401) {
        window.location.href = "/login.html";
        throw new Error("Unauthorized");
    }

    if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Request failed: ${response.status}`);
    }

    const payload = await response.json();
    if (
        payload &&
        typeof payload === "object" &&
        !Array.isArray(payload) &&
        payload.status === "error"
    ) {
        const errorMessage =
            payload.error && payload.error.message
                ? payload.error.message
                : "Request failed";
        throw new Error(errorMessage);
    }

    return payload;
}

async function loadChannels() {
    try {
        const data = await apiJson("/api/my-channels", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: "{}"
        });

        currentUser = String(data.user || "").trim();
        const channels = Array.isArray(data.channels) ? data.channels : [];
        const list = document.getElementById("channel-list");
        list.replaceChildren();

        channels.forEach((channel) => {
            const li = document.createElement("li");
            li.textContent = "# " + channel;
            li.onclick = () => selectChannel(channel);
            list.appendChild(li);
        });

        if (channels.length === 0) {
            currentChannel = "";
            document.getElementById("current-channel").textContent = "# no channel";
            renderMessages([]);
            return;
        }

        if (!channels.includes(currentChannel)) {
            selectChannel(channels[0]);
        } else {
            pollMessages(true);
        }
    } catch (error) {
        console.error("loadChannels failed", error);
    }
}

function selectChannel(channel) {
    if (!channel) {
        return;
    }

    currentChannel = channel;
    document.getElementById("current-channel").textContent = "# " + channel;
    renderMessages([]);
    pollMessages(true);
}

async function pollMessages(forceRender = false) {
    if (!currentChannel) {
        return;
    }

    const channelAtRequest = currentChannel;
    const pollId = ++latestPollId;

    try {
        const messages = await apiJson("/api/get-messages", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ channel: channelAtRequest })
        });

        if (pollId !== latestPollId || channelAtRequest !== currentChannel) {
            return;
        }

        const safeMessages = Array.isArray(messages) ? messages : [];
        const previousCount = messageCountByChannel.get(channelAtRequest);
        if (forceRender || previousCount !== safeMessages.length) {
            messageCountByChannel.set(channelAtRequest, safeMessages.length);
            renderMessages(safeMessages);
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
        const sender = String(message.sender || "anonymous");
        const senderLabel = currentUser && sender === currentUser ? "me" : sender;
        senderSpan.textContent = `${senderLabel}:`;

        div.appendChild(timeSpan);
        div.appendChild(document.createTextNode(" "));
        div.appendChild(senderSpan);
        div.appendChild(document.createTextNode(" "));
        div.appendChild(document.createTextNode(String(message.message || "")));

        container.appendChild(div);
    });

    container.scrollTop = container.scrollHeight;
}

async function sendMessage() {
    if (!currentChannel) {
        return;
    }

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
                message
            })
        });

        input.value = "";
        pollMessages(true);
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
            body: JSON.stringify({ channel })
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
            body: JSON.stringify({ channel })
        });

        input.value = "";
        await loadChannels();
        selectChannel(channel);
    } catch (error) {
        console.error("joinChannel failed", error);
    }
}

function bindSendOnEnter() {
    const input = document.getElementById("msg-input");
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            sendMessage();
        }
    });
}

window.onload = () => {
    bindSendOnEnter();
    loadChannels();
    setInterval(() => {
        pollMessages(false);
    }, 2000);
};
