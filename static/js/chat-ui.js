const MODE_CHANNEL = "channel";
const MODE_P2P = "p2p";

const COMPOSER_NONE = "";
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
let manualNoSelection = false;

let latestViewToken = 0;
let sendInFlight = false;
let toastTimer = null;
let modalResolver = null;

function normalizeText(value) {
    return String(value || "").trim();
}

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

function peerLabelById(peerId) {
    const safePeerId = normalizeText(peerId);
    if (!safePeerId) {
        return "";
    }

    const found = knownPeers.find((peer) => normalizeText(peer.peer_id) === safePeerId);
    if (!found) {
        return safePeerId;
    }

    return normalizeText(found.user_id) || safePeerId;
}

function peerDisplayLabelFromObject(peer) {
    const peerId = normalizeText(peer.peer_id);
    const userId = normalizeText(peer.user_id);

    if (!peerId && !userId) {
        return "unknown";
    }

    if (userId && peerId && userId !== peerId) {
        return `${userId} (${peerId})`;
    }

    return userId || peerId;
}

function updateAccountStrip() {
    document.getElementById("account-user").textContent = `User: ${currentUser || "-"}`;
    document.getElementById("account-peer-id").textContent = `Peer ID: ${localPeerId || "-"}`;
}

function closeAllRowMenus() {
    document.querySelectorAll(".row-menu.open").forEach((node) => {
        node.classList.remove("open");
        node.style.left = "";
        node.style.top = "";
    });
}

function openRowMenu(menu, triggerButton) {
    const rect = triggerButton.getBoundingClientRect();
    const menuWidth = 220;
    const viewportPadding = 8;
    let left = rect.right - menuWidth;
    let top = rect.bottom + 6;

    if (left < viewportPadding) {
        left = viewportPadding;
    }

    if (top > window.innerHeight - 120) {
        top = Math.max(viewportPadding, rect.top - 92);
    }

    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
    menu.classList.add("open");
}

function getModalNodes() {
    return {
        root: document.getElementById("action-modal"),
        title: document.getElementById("action-modal-title"),
        message: document.getElementById("action-modal-message"),
        input: document.getElementById("action-modal-input"),
        cancel: document.getElementById("action-modal-cancel"),
        confirm: document.getElementById("action-modal-confirm")
    };
}

function closeActionModal(result) {
    const nodes = getModalNodes();
    if (nodes.root) {
        nodes.root.classList.remove("visible");
    }

    if (modalResolver) {
        const resolver = modalResolver;
        modalResolver = null;
        resolver(result || { confirmed: false, value: "" });
    }
}

function openActionModal(options = {}) {
    const nodes = getModalNodes();
    if (!nodes.root) {
        return Promise.resolve({ confirmed: false, value: "" });
    }

    if (modalResolver) {
        closeActionModal({ confirmed: false, value: "" });
    }

    const title = normalizeText(options.title) || "Confirm Action";
    const message = normalizeText(options.message);
    const confirmLabel = normalizeText(options.confirmLabel) || "Confirm";
    const cancelLabel = normalizeText(options.cancelLabel) || "Cancel";
    const inputVisible = Boolean(options.inputVisible);
    const inputValue = normalizeText(options.inputValue);
    const inputPlaceholder = normalizeText(options.inputPlaceholder);
    const danger = Boolean(options.danger);

    nodes.title.textContent = title;
    nodes.message.textContent = message;
    nodes.cancel.textContent = cancelLabel;
    nodes.confirm.textContent = confirmLabel;
    nodes.confirm.classList.toggle("danger", danger);

    if (inputVisible) {
        nodes.input.value = inputValue;
        nodes.input.placeholder = inputPlaceholder;
        nodes.input.classList.remove("hidden");
    } else {
        nodes.input.value = "";
        nodes.input.classList.add("hidden");
    }

    nodes.root.classList.add("visible");
    if (inputVisible) {
        nodes.input.focus();
        nodes.input.select();
    } else {
        nodes.confirm.focus();
    }

    return new Promise((resolve) => {
        modalResolver = resolve;
    });
}

async function promptRename(kindLabel, currentName) {
    const outcome = await openActionModal({
        title: `Rename ${kindLabel}`,
        message: `Update the ${kindLabel} name.`,
        confirmLabel: "Save",
        cancelLabel: "Cancel",
        inputVisible: true,
        inputValue: currentName,
        inputPlaceholder: `New ${kindLabel} name`
    });

    if (!outcome.confirmed) {
        return "";
    }

    return normalizeText(outcome.value);
}

async function confirmLeave(kindLabel, name) {
    const outcome = await openActionModal({
        title: `Leave ${kindLabel}`,
        message: `Leave '${name}'? This removes it from your list.`,
        confirmLabel: "Leave",
        cancelLabel: "Cancel",
        danger: true
    });

    return Boolean(outcome.confirmed);
}

function setComposerMode(mode) {
    composerMode = mode;

    const shell = document.getElementById("workspace-tools");
    const p2pComposer = document.getElementById("p2p-composer");

    shell.classList.remove("visible");
    p2pComposer.classList.remove("visible");

    if (mode === COMPOSER_P2P) {
        shell.classList.add("visible");
        p2pComposer.classList.add("visible");
        document.getElementById("peer-search-input").focus();
        renderPeerSearchResults();
    }
}

function updateChatInputState() {
    const inputArea = document.getElementById("input-area");
    const input = document.getElementById("msg-input");
    const sendButton = document.getElementById("send-btn");
    const closeButton = document.getElementById("close-conversation-btn");
    const hasSelection = Boolean(currentTarget.mode && currentTarget.id);

    input.disabled = !hasSelection;
    sendButton.disabled = !hasSelection;
    inputArea.classList.toggle("disabled", !hasSelection);
    closeButton.classList.toggle("hidden", !hasSelection);

    if (hasSelection) {
        input.placeholder = "Type a message and press Enter";
        return;
    }

    input.placeholder = "Select a conversation to start chatting";
}

function setTarget(mode, id, title, subtitle) {
    if (mode && id) {
        manualNoSelection = false;
    }

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
    updateChatInputState();
}

function clearConversationSelection() {
    manualNoSelection = true;
    setTarget("", "", "No room selected", "Choose a channel or conversation from the left panel.");
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
    menu.addEventListener("click", (event) => {
        event.stopPropagation();
    });

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
            openRowMenu(menu, menuButton);
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
        empty.className = "empty-state";
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
                const safeName = await promptRename("channel", channel);
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
                if (!(await confirmLeave("channel", channel))) {
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
        empty.className = "empty-state";
        empty.textContent = "No conversations yet";
        list.appendChild(empty);
        return;
    }

    knownP2PRooms.forEach((room) => {
        const peerText = Array.isArray(room.peers) ? room.peers.map(peerLabelById).join(", ") : "";
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
                const safeName = await promptRename("conversation", room.room_name);
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
                if (!(await confirmLeave("conversation", room.room_name))) {
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

    const query = normalizeText(document.getElementById("peer-search-input").value).toLowerCase();
    if (!query) {
        list.classList.remove("visible");
        return;
    }

    const matches = knownPeers.filter((peer) => {
        const peerId = normalizeText(peer.peer_id);
        const userId = normalizeText(peer.user_id);
        const matchesQuery = peerId.toLowerCase().includes(query) || userId.toLowerCase().includes(query);
        return matchesQuery && peerId !== localPeerId && !selectedPeerIds.includes(peerId);
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
        const endpoint = `(${normalizeText(peer.ip)}:${String(peer.port || 0)})`;
        li.textContent = `${peerDisplayLabelFromObject(peer)} ${endpoint}`;
        li.addEventListener("click", () => {
            addSelectedPeer(normalizeText(peer.peer_id));
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
    chip.appendChild(document.createTextNode(peerLabelById(peerId) || peerId));

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
    const safe = normalizeText(peerId);
    if (!safe || selectedPeerIds.includes(safe)) {
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

    const labels = peers.map((peerId) => peerLabelById(peerId) || peerId);
    if (labels.length <= 2) {
        return `P2P: ${labels.join(", ")}`;
    }

    return `P2P: ${labels[0]}, ${labels[1]} +${labels.length - 2}`;
}

async function loadChannels() {
    const data = await apiJson("/api/my-channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}"
    });

    currentUser = normalizeText(data.user);
    localPeerId = normalizeText(data.peer_id);
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
    knownPeers = (Array.isArray(data.peers) ? data.peers : []).filter((peer) => {
        return normalizeText(peer.peer_id) !== localPeerId;
    });
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
        if (manualNoSelection) {
            return;
        }

        if (knownChannels.length > 0) {
            setTarget(MODE_CHANNEL, knownChannels[0], `# ${knownChannels[0]}`, "Public channel conversation");
            return;
        }

        if (knownP2PRooms.length > 0) {
            const room = knownP2PRooms[0];
            const peerText = Array.isArray(room.peers) ? room.peers.map(peerLabelById).join(", ") : "";
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
    const message = normalizeText(input.value);
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

async function upsertChannel(channel) {
    const safeChannel = normalizeText(channel);
    if (!safeChannel) {
        showToast("Channel name is required", true);
        return;
    }

    await apiJson("/api/channel-upsert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel: safeChannel })
    });

    await refreshSidebarData();
    setTarget(MODE_CHANNEL, safeChannel, `# ${safeChannel}`, "Public channel conversation");
    await refreshCurrentMessages();
}

async function openChannelCreateFlow() {
    clearConversationSelection();
    setComposerMode(COMPOSER_NONE);

    const outcome = await openActionModal({
        title: "Add or Join Channel",
        message: "Enter the channel name you want to join or create.",
        confirmLabel: "Continue",
        cancelLabel: "Cancel",
        inputVisible: true,
        inputPlaceholder: "Channel name"
    });

    if (!outcome.confirmed) {
        return;
    }

    await upsertChannel(outcome.value);
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
    const peerText = Array.isArray(room.peers) ? room.peers.map(peerLabelById).join(", ") : "";
    setTarget(
        MODE_P2P,
        room.room_id,
        room.room_name,
        peerText ? `Peers: ${peerText}` : "Private conversation"
    );
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
    window.addEventListener("resize", closeAllRowMenus);
    window.addEventListener("scroll", closeAllRowMenus, true);

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
        openChannelCreateFlow().catch((error) => {
            showToast(error.message || "Unable to join/create channel", true);
        });
    });

    document.getElementById("new-p2p-btn").addEventListener("click", () => {
        if (composerMode === COMPOSER_P2P) {
            setComposerMode(COMPOSER_NONE);
            return;
        }
        setComposerMode(COMPOSER_P2P);
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
    document.getElementById("close-conversation-btn").addEventListener("click", () => {
        closeAllRowMenus();
        clearConversationSelection();
    });

    const modal = document.getElementById("action-modal");
    const modalInput = document.getElementById("action-modal-input");
    const modalCancel = document.getElementById("action-modal-cancel");
    const modalConfirm = document.getElementById("action-modal-confirm");

    modal.addEventListener("click", (event) => {
        if (event.target === modal) {
            closeActionModal({ confirmed: false, value: "" });
        }
    });

    modalCancel.addEventListener("click", () => {
        closeActionModal({ confirmed: false, value: "" });
    });

    modalConfirm.addEventListener("click", () => {
        closeActionModal({ confirmed: true, value: modalInput.value });
    });

    modalInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            closeActionModal({ confirmed: true, value: modalInput.value });
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && modal.classList.contains("visible")) {
            event.preventDefault();
            closeActionModal({ confirmed: false, value: "" });
        }
    });
}

async function initialize() {
    bindUi();
    renderSelectedPeerSelection();
    updateChatInputState();

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
        if (document.querySelector(".row-menu.open")) {
            return;
        }
        if (document.getElementById("action-modal")?.classList.contains("visible")) {
            return;
        }

        refreshSidebarData().catch((error) => {
            console.error("sidebar refresh failed", error);
        });
    }, 5000);
}

window.addEventListener("load", initialize);
