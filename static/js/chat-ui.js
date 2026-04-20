const MODE_CHANNEL = "channel";
const MODE_P2P = "p2p";

const COMPOSER_NONE = "";
const COMPOSER_CHANNEL = "channel";
const COMPOSER_P2P = "p2p";

let currentUser = "";
let localPeerId = "";

let currentTarget = {
    mode: "",
    id: "",
    title: "No room selected",
    subtitle: "Choose a channel or conversation from the left panel."
};

let composerMode = COMPOSER_NONE;
let knownChannels = [];
let knownP2PRooms = [];
let knownPeers = [];

let selectedPeerIds = [];
let selectedPeerExpanded = false;

let latestViewToken = 0;
let sendInFlight = false;
let toastTimer = null;

function showToast(message, isError = false) {
    const toast = document.getElementById("toast");
    toast.textContent = String(message || "");
    toast.style.display = "block";
    toast.style.background = isError ? "#b91c1c" : "#067f74";

    if (toastTimer) {
        window.clearTimeout(toastTimer);
    }

    toastTimer = window.setTimeout(() => {
        toast.style.display = "none";
    }, 3200);
}

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
    if (payload && typeof payload === "object" && !Array.isArray(payload)) {
        if (payload.status === "error") {
            const message =
                payload.error && payload.error.message
                    ? payload.error.message
                    : (payload.message || "Request failed");
            throw new Error(message);
        }
    }

    return payload;
}

function computeLocalPeerId(username) {
    const host = window.location.hostname || "local";
    const port = window.location.port || "default";
    return `${username || "anonymous"}@${host}:${port}`;
}

function updateAccountStrip() {
    document.getElementById("session-user").textContent = currentUser
        ? `Signed in as ${currentUser}`
        : "Signed in";
    document.getElementById("account-user").textContent = `User: ${currentUser || "-"}`;
    document.getElementById("account-peer-id").textContent = `Peer ID: ${localPeerId || "-"}`;
}

function closeAllRowMenus() {
    document.querySelectorAll(".row-menu.open").forEach((node) => {
        node.classList.remove("open");
    });
}

function setComposerMode(mode) {
    composerMode = mode;

    const shell = document.getElementById("workspace-tools");
    const channelComposer = document.getElementById("channel-composer");
    const p2pComposer = document.getElementById("p2p-composer");

    shell.classList.remove("visible");
    channelComposer.classList.remove("visible");
    p2pComposer.classList.remove("visible");

    if (mode === COMPOSER_CHANNEL) {
        shell.classList.add("visible");
        channelComposer.classList.add("visible");
        document.getElementById("channel-input").focus();
        return;
    }

    if (mode === COMPOSER_P2P) {
        shell.classList.add("visible");
        p2pComposer.classList.add("visible");
        document.getElementById("peer-search-input").focus();
        renderPeerSearchResults();
    }
}

function setTarget(mode, id, title, subtitle) {
    currentTarget = {
        mode,
        id,
        title: title || "No room selected",
        subtitle: subtitle || ""
    };
    latestViewToken += 1;

    document.getElementById("current-room-title").textContent = currentTarget.title;
    document.getElementById("current-room-subtitle").textContent = currentTarget.subtitle;

    setComposerMode(COMPOSER_NONE);
    renderMessages([]);
    renderChannelList();
    renderP2PRoomList();
}

function renderMessages(messages) {
    const container = document.getElementById("messages");
    container.replaceChildren();

    messages.forEach((message) => {
        const row = document.createElement("div");
        row.className = "msg";

        const time = document.createElement("span");
        time.className = "msg-time";
        time.textContent = `[${String(message.timestamp || "")}]`;

        const senderNode = document.createElement("span");
        senderNode.className = "msg-sender";
        const sender = String(message.sender || "anonymous");
        let senderLabel = sender;
        if (sender === currentUser) {
            senderLabel = "me";
        } else if (sender === "me") {
            senderLabel = "legacy-user";
        }
        senderNode.textContent = `${senderLabel}:`;

        row.appendChild(time);
        row.appendChild(document.createTextNode(" "));
        row.appendChild(senderNode);
        row.appendChild(document.createTextNode(" "));
        row.appendChild(document.createTextNode(String(message.message || "")));
        container.appendChild(row);
    });

    container.scrollTop = container.scrollHeight;
}

function buildSidebarItem(config) {
    const li = document.createElement("li");
    if (config.active) {
        li.classList.add("active");
    }

    const mainButton = document.createElement("button");
    mainButton.type = "button";
    mainButton.className = "row-main";
    mainButton.textContent = config.label;
    mainButton.addEventListener("click", () => {
        closeAllRowMenus();
        config.onSelect();
    });

    const menuButton = document.createElement("button");
    menuButton.type = "button";
    menuButton.className = "row-menu-trigger";
    menuButton.textContent = "...";

    const menu = document.createElement("div");
    menu.className = "row-menu";

    const renameBtn = document.createElement("button");
    renameBtn.type = "button";
    renameBtn.textContent = `Rename ${config.kind}`;
    renameBtn.addEventListener("click", async (event) => {
        event.stopPropagation();
        closeAllRowMenus();
        await config.onRename();
    });

    const leaveBtn = document.createElement("button");
    leaveBtn.type = "button";
    leaveBtn.className = "leave";
    leaveBtn.textContent = `Leave ${config.kind}`;
    leaveBtn.addEventListener("click", async (event) => {
        event.stopPropagation();
        closeAllRowMenus();
        await config.onLeave();
    });

    menu.appendChild(renameBtn);
    menu.appendChild(leaveBtn);

    menuButton.addEventListener("click", (event) => {
        event.stopPropagation();
        const willOpen = !menu.classList.contains("open");
        closeAllRowMenus();
        if (willOpen) {
            menu.classList.add("open");
        }
    });

    li.appendChild(mainButton);
    li.appendChild(menuButton);
    li.appendChild(menu);
    return li;
}

function renderChannelList() {
    const list = document.getElementById("channel-list");
    list.replaceChildren();

    if (knownChannels.length === 0) {
        const empty = document.createElement("li");
        empty.textContent = "No channels yet";
        list.appendChild(empty);
        return;
    }

    knownChannels.forEach((channel) => {
        const item = buildSidebarItem({
            label: `# ${channel}`,
            kind: "channel",
            active: currentTarget.mode === MODE_CHANNEL && currentTarget.id === channel,
            onSelect: async () => {
                setTarget(MODE_CHANNEL, channel, `# ${channel}`, "Public channel conversation");
                await refreshCurrentMessages();
            },
            onRename: async () => {
                const newName = window.prompt("Rename channel", channel);
                if (newName === null) {
                    return;
                }
                const safeName = String(newName).trim();
                if (!safeName || safeName === channel) {
                    return;
                }

                await apiJson("/api/channel/rename", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ channel, new_name: safeName })
                });

                const wasActive = currentTarget.mode === MODE_CHANNEL && currentTarget.id === channel;
                await refreshSidebarData();
                if (wasActive) {
                    setTarget(MODE_CHANNEL, safeName, `# ${safeName}`, "Public channel conversation");
                    await refreshCurrentMessages();
                }
            },
            onLeave: async () => {
                if (!window.confirm(`Leave channel '${channel}'?`)) {
                    return;
                }

                const wasActive = currentTarget.mode === MODE_CHANNEL && currentTarget.id === channel;
                await apiJson("/api/channel/leave", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ channel })
                });

                await refreshSidebarData();
                if (wasActive) {
                    ensureActiveTarget();
                    await refreshCurrentMessages();
                }
            }
        });
        list.appendChild(item);
    });
}

function renderP2PRoomList() {
    const list = document.getElementById("p2p-room-list");
    list.replaceChildren();

    if (knownP2PRooms.length === 0) {
        const empty = document.createElement("li");
        empty.textContent = "No conversations yet";
        list.appendChild(empty);
        return;
    }

    knownP2PRooms.forEach((room) => {
        const peerText = Array.isArray(room.peers) ? room.peers.join(", ") : "";
        const item = buildSidebarItem({
            label: room.room_name,
            kind: "conversation",
            active: currentTarget.mode === MODE_P2P && currentTarget.id === room.room_id,
            onSelect: async () => {
                setTarget(
                    MODE_P2P,
                    room.room_id,
                    room.room_name,
                    peerText ? `Peers: ${peerText}` : "Private conversation"
                );
                await refreshCurrentMessages();
            },
            onRename: async () => {
                const newName = window.prompt("Rename conversation", room.room_name);
                if (newName === null) {
                    return;
                }
                const safeName = String(newName).trim();
                if (!safeName || safeName === room.room_name) {
                    return;
                }

                await apiJson("/api/p2p/rename", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ room_id: room.room_id, new_name: safeName })
                });

                const wasActive = currentTarget.mode === MODE_P2P && currentTarget.id === room.room_id;
                await refreshSidebarData();
                if (wasActive) {
                    setTarget(
                        MODE_P2P,
                        room.room_id,
                        safeName,
                        peerText ? `Peers: ${peerText}` : "Private conversation"
                    );
                    await refreshCurrentMessages();
                }
            },
            onLeave: async () => {
                if (!window.confirm(`Leave conversation '${room.room_name}'?`)) {
                    return;
                }

                const wasActive = currentTarget.mode === MODE_P2P && currentTarget.id === room.room_id;
                await apiJson("/api/p2p/leave", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ room_id: room.room_id })
                });

                await refreshSidebarData();
                if (wasActive) {
                    ensureActiveTarget();
                    await refreshCurrentMessages();
                }
            }
        });
        list.appendChild(item);
    });
}

function renderPeerSearchResults() {
    const list = document.getElementById("p2p-peer-search-results");
    list.replaceChildren();

    if (composerMode !== COMPOSER_P2P) {
        list.classList.remove("visible");
        return;
    }

    const query = String(document.getElementById("peer-search-input").value || "")
        .trim()
        .toLowerCase();
    if (!query) {
        list.classList.remove("visible");
        return;
    }

    const matches = knownPeers.filter((peer) => {
        const id = String(peer.peer_id || "").toLowerCase();
        return id.includes(query) && !selectedPeerIds.includes(String(peer.peer_id));
    });

    if (matches.length === 0) {
        const empty = document.createElement("li");
        empty.textContent = "No peer found";
        list.appendChild(empty);
        list.classList.add("visible");
        return;
    }

    matches.forEach((peer) => {
        const li = document.createElement("li");
        li.textContent = `${peer.peer_id} (${peer.ip}:${peer.port})`;
        li.addEventListener("click", () => {
            addSelectedPeer(String(peer.peer_id));
        });
        list.appendChild(li);
    });

    list.classList.add("visible");
}

function removeSelectedPeer(peerId) {
    selectedPeerIds = selectedPeerIds.filter((item) => item !== peerId);
    if (selectedPeerIds.length <= 3) {
        selectedPeerExpanded = false;
    }
    renderSelectedPeerSelection();
}

function makePeerChip(peerId) {
    const chip = document.createElement("span");
    chip.className = "peer-chip";
    chip.appendChild(document.createTextNode(peerId));

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.textContent = "x";
    removeBtn.addEventListener("click", () => {
        removeSelectedPeer(peerId);
    });
    chip.appendChild(removeBtn);
    return chip;
}

function renderSelectedPeerSelection() {
    const preview = document.getElementById("selected-peer-preview");
    const overflow = document.getElementById("selected-peer-overflow");
    const toggle = document.getElementById("peer-overflow-toggle");

    preview.replaceChildren();
    overflow.replaceChildren();

    const previewLimit = 3;
    const hiddenCount = Math.max(0, selectedPeerIds.length - previewLimit);

    selectedPeerIds.slice(0, previewLimit).forEach((peerId) => {
        preview.appendChild(makePeerChip(peerId));
    });

    if (hiddenCount > 0) {
        const ellipsis = document.createElement("span");
        ellipsis.className = "peer-chip";
        ellipsis.appendChild(document.createTextNode("..."));
        preview.appendChild(ellipsis);
        toggle.classList.remove("hidden");
        toggle.textContent = selectedPeerExpanded ? "... ▴" : "... ▾";
    } else {
        toggle.classList.add("hidden");
        selectedPeerExpanded = false;
    }

    if (selectedPeerExpanded && hiddenCount > 0) {
        selectedPeerIds.forEach((peerId) => {
            overflow.appendChild(makePeerChip(peerId));
        });
        overflow.classList.remove("hidden");
    } else {
        overflow.classList.add("hidden");
    }
}

function addSelectedPeer(peerId) {
    const safe = String(peerId || "").trim();
    if (!safe) {
        return;
    }
    if (selectedPeerIds.includes(safe)) {
        return;
    }

    selectedPeerIds.push(safe);
    document.getElementById("peer-search-input").value = "";
    selectedPeerExpanded = false;
    renderSelectedPeerSelection();
    renderPeerSearchResults();
}

function buildPrivateRoomName(peers) {
    if (!Array.isArray(peers) || peers.length === 0) {
        return "Private Conversation";
    }
    if (peers.length <= 2) {
        return `P2P: ${peers.join(", ")}`;
    }
    return `P2P: ${peers[0]}, ${peers[1]} +${peers.length - 2}`;
}

async function loadChannels() {
    const data = await apiJson("/api/my-channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}"
    });

    currentUser = String(data.user || "").trim();
    localPeerId = computeLocalPeerId(currentUser);
    updateAccountStrip();

    knownChannels = Array.isArray(data.channels) ? data.channels : [];
    renderChannelList();
}

async function loadP2PRooms() {
    const data = await apiJson("/api/p2p/rooms", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}"
    });
    knownP2PRooms = Array.isArray(data.rooms) ? data.rooms : [];
    renderP2PRoomList();
}

async function loadPeerCatalog() {
    const data = await apiJson("/api/online-peers", { method: "GET" });
    knownPeers = Array.isArray(data.peers) ? data.peers : [];
    renderPeerSearchResults();
}

function ensureActiveTarget() {
    if (currentTarget.mode === MODE_CHANNEL && !knownChannels.includes(currentTarget.id)) {
        currentTarget.mode = "";
        currentTarget.id = "";
    }

    if (currentTarget.mode === MODE_P2P) {
        const exists = knownP2PRooms.some((room) => room.room_id === currentTarget.id);
        if (!exists) {
            currentTarget.mode = "";
            currentTarget.id = "";
        }
    }

    if (!currentTarget.mode) {
        if (knownChannels.length > 0) {
            setTarget(MODE_CHANNEL, knownChannels[0], `# ${knownChannels[0]}`, "Public channel conversation");
            return;
        }

        if (knownP2PRooms.length > 0) {
            const room = knownP2PRooms[0];
            const peerText = Array.isArray(room.peers) ? room.peers.join(", ") : "";
            setTarget(
                MODE_P2P,
                room.room_id,
                room.room_name,
                peerText ? `Peers: ${peerText}` : "Private conversation"
            );
            return;
        }

        setTarget("", "", "No room selected", "Use + Add/Create or + New P2P from the left side.");
    }
}

async function refreshSidebarData() {
    await loadChannels();
    await Promise.all([loadPeerCatalog(), loadP2PRooms()]);
    ensureActiveTarget();
}

async function refreshCurrentMessages() {
    if (!currentTarget.mode || !currentTarget.id) {
        renderMessages([]);
        return;
    }

    const token = latestViewToken;
    if (currentTarget.mode === MODE_CHANNEL) {
        const messages = await apiJson("/api/get-messages", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ channel: currentTarget.id })
        });

        if (token !== latestViewToken) {
            return;
        }

        renderMessages(Array.isArray(messages) ? messages : []);
        return;
    }

    const payload = await apiJson("/api/p2p/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ room_id: currentTarget.id })
    });

    if (token !== latestViewToken) {
        return;
    }

    renderMessages(Array.isArray(payload.messages) ? payload.messages : []);
}

async function sendMessage() {
    if (sendInFlight) {
        return;
    }

    if (!currentTarget.mode || !currentTarget.id) {
        showToast("Select a conversation first", true);
        return;
    }

    const input = document.getElementById("msg-input");
    const message = String(input.value || "").trim();
    if (!message) {
        return;
    }

    sendInFlight = true;
    try {
        if (currentTarget.mode === MODE_CHANNEL) {
            await apiJson("/api/send-channel", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ channel: currentTarget.id, message })
            });
        } else {
            await apiJson("/api/p2p/send-room", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ room_id: currentTarget.id, message })
            });
            await loadP2PRooms();
        }

        input.value = "";
        await refreshCurrentMessages();
    } catch (error) {
        showToast(error.message || "Send failed", true);
    } finally {
        sendInFlight = false;
    }
}

async function upsertChannelFromComposer() {
    const channelInput = document.getElementById("channel-input");
    const channel = String(channelInput.value || "").trim();
    if (!channel) {
        showToast("Channel name is required", true);
        return;
    }

    await apiJson("/api/channel-upsert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel })
    });

    channelInput.value = "";
    await refreshSidebarData();
    setTarget(MODE_CHANNEL, channel, `# ${channel}`, "Public channel conversation");
    await refreshCurrentMessages();
}

async function createP2PRoomFromComposer() {
    const peers = selectedPeerIds.slice();
    if (peers.length === 0) {
        showToast("Add at least one peer ID", true);
        return;
    }

    const payload = await apiJson("/api/p2p/create-room", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            peers,
            room_name: buildPrivateRoomName(peers)
        })
    });

    selectedPeerIds = [];
    selectedPeerExpanded = false;
    document.getElementById("peer-search-input").value = "";
    renderSelectedPeerSelection();
    renderPeerSearchResults();

    await loadP2PRooms();
    const room = payload.room;
    const peerText = Array.isArray(room.peers) ? room.peers.join(", ") : "";
    setTarget(MODE_P2P, room.room_id, room.room_name, peerText ? `Peers: ${peerText}` : "Private conversation");
    await refreshCurrentMessages();
}

async function logout() {
    try {
        await fetch("/logout", {
            method: "POST",
            credentials: "same-origin"
        });
    } finally {
        window.location.href = "/login.html";
    }
}

function bindUi() {
    document.addEventListener("click", () => {
        closeAllRowMenus();
    });

    document.getElementById("send-btn").addEventListener("click", () => {
        sendMessage().catch((error) => {
            showToast(error.message || "Send failed", true);
        });
    });

    document.getElementById("msg-input").addEventListener("keydown", (event) => {
        if (event.key !== "Enter") {
            return;
        }
        if (event.repeat) {
            return;
        }
        event.preventDefault();
        sendMessage().catch((error) => {
            showToast(error.message || "Send failed", true);
        });
    });

    document.getElementById("new-channel-btn").addEventListener("click", () => {
        if (composerMode === COMPOSER_CHANNEL) {
            setComposerMode(COMPOSER_NONE);
            return;
        }
        setComposerMode(COMPOSER_CHANNEL);
    });

    document.getElementById("new-p2p-btn").addEventListener("click", () => {
        if (composerMode === COMPOSER_P2P) {
            setComposerMode(COMPOSER_NONE);
            return;
        }
        setComposerMode(COMPOSER_P2P);
    });

    document.getElementById("channel-upsert-btn").addEventListener("click", () => {
        upsertChannelFromComposer().catch((error) => {
            showToast(error.message || "Unable to join/create channel", true);
        });
    });

    document.getElementById("peer-search-input").addEventListener("input", () => {
        renderPeerSearchResults();
    });

    document.getElementById("peer-overflow-toggle").addEventListener("click", () => {
        selectedPeerExpanded = !selectedPeerExpanded;
        renderSelectedPeerSelection();
    });

    document.getElementById("create-private-room-btn").addEventListener("click", () => {
        createP2PRoomFromComposer().catch((error) => {
            showToast(error.message || "Unable to create conversation", true);
        });
    });

    document.getElementById("logout-btn").addEventListener("click", logout);
}

async function initialize() {
    bindUi();
    renderSelectedPeerSelection();

    try {
        await refreshSidebarData();
        await refreshCurrentMessages();
    } catch (error) {
        showToast(error.message || "Initialization failed", true);
    }

    window.setInterval(() => {
        refreshCurrentMessages().catch((error) => {
            console.error("message refresh failed", error);
        });
    }, 2000);

    window.setInterval(() => {
        refreshSidebarData().catch((error) => {
            console.error("sidebar refresh failed", error);
        });
    }, 5000);
}

window.addEventListener("load", initialize);
