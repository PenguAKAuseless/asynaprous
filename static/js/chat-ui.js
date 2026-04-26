const MODE_CHANNEL = "channel";
const MODE_P2P = "p2p";

const COMPOSER_NONE = "";
const COMPOSER_P2P = "p2p";

const STORAGE_NAMESPACE = "asynaprous-p2p-v2";
const P2P_MESSAGE_LIMIT = 2000;

const SIGNAL_POLL_TIMEOUT_SECONDS = 25;
const CHANNEL_POLL_TIMEOUT_SECONDS = 25;
const RETRY_DELAY_MS = 1400;

const RTC_CONFIG = {
    iceServers: [
        { urls: ["stun:stun.l.google.com:19302"] }
    ]
};

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
let knownPeers = [];
let knownP2PRooms = [];

let selectedPeerIds = [];
let selectedPeerExpanded = false;
let manualNoSelection = false;

let latestViewToken = 0;
let sendInFlight = false;
let toastTimer = null;
let modalResolver = null;

let signalLoopToken = 0;
let signalLastEventId = 0;
let channelLoopToken = 0;
let peerCatalogRefreshInFlight = false;
let lastPeerCatalogRefreshAtMs = 0;
let peerDbSearchInFlight = false;
let lastPeerDbSearchQuery = "";
let lastPeerDbSearchAtMs = 0;

let channelSeqById = {};
let channelMessagesById = {};
let roomMessagesById = {};

const peerConnections = new Map();

function normalizeText(value) {
    return String(value || "").trim();
}

function normalizePeerId(value) {
    return normalizeText(value).toLowerCase();
}

function delay(ms) {
    return new Promise((resolve) => {
        window.setTimeout(resolve, ms);
    });
}

function nowIso() {
    return new Date().toISOString();
}

function formatTimestamp(inputIso) {
    const value = normalizeText(inputIso);
    if (!value) {
        return "";
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }

    const hh = String(date.getHours()).padStart(2, "0");
    const mm = String(date.getMinutes()).padStart(2, "0");
    const ss = String(date.getSeconds()).padStart(2, "0");
    return `${hh}:${mm}:${ss}`;
}

function makeUuid() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
        return window.crypto.randomUUID();
    }

    return `u${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

function readStorageJson(key, fallbackValue) {
    try {
        const raw = localStorage.getItem(key);
        if (!raw) {
            return fallbackValue;
        }

        const parsed = JSON.parse(raw);
        if (parsed === null || parsed === undefined) {
            return fallbackValue;
        }

        return parsed;
    } catch (error) {
        console.error("storage read failed", error);
        return fallbackValue;
    }
}

function writeStorageJson(key, value) {
    try {
        localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
        console.error("storage write failed", error);
    }
}

function roomsStorageKey() {
    return `${STORAGE_NAMESPACE}:rooms:${localPeerId || "anonymous"}`;
}

function roomMessagesStorageKey(roomId) {
    return `${STORAGE_NAMESPACE}:messages:${localPeerId || "anonymous"}:${roomId}`;
}

function sanitizePeerIds(peerIds) {
    const output = [];
    const seen = new Set();

    for (const peerId of Array.isArray(peerIds) ? peerIds : []) {
        const safePeerId = normalizePeerId(peerId);
        if (!safePeerId || seen.has(safePeerId) || safePeerId === localPeerId) {
            continue;
        }

        seen.add(safePeerId);
        output.push(safePeerId);
    }

    return output;
}

function sortRoomsByRecent(rooms) {
    const copy = Array.isArray(rooms) ? rooms.slice() : [];
    copy.sort((left, right) => {
        const leftTime = Date.parse(normalizeText(left.updated_at) || "1970-01-01T00:00:00.000Z");
        const rightTime = Date.parse(normalizeText(right.updated_at) || "1970-01-01T00:00:00.000Z");
        return rightTime - leftTime;
    });
    return copy;
}

function loadP2PRoomsFromStorage() {
    const stored = readStorageJson(roomsStorageKey(), []);
    const sanitized = [];

    for (const room of Array.isArray(stored) ? stored : []) {
        const roomId = normalizeText(room.room_id);
        if (!roomId) {
            continue;
        }

        const peers = sanitizePeerIds(room.peers);
        sanitized.push({
            room_id: roomId,
            room_name: normalizeText(room.room_name) || "Private Conversation",
            peers,
            type: normalizeText(room.type) || (peers.length <= 1 ? "direct" : "private"),
            updated_at: normalizeText(room.updated_at) || nowIso()
        });
    }

    knownP2PRooms = sortRoomsByRecent(sanitized);
    roomMessagesById = {};
}

async function refreshPeerCatalogForSearch(force = false) {
    const nowMs = Date.now();
    if (!force && (peerCatalogRefreshInFlight || nowMs - lastPeerCatalogRefreshAtMs < 3000)) {
        return;
    }

    peerCatalogRefreshInFlight = true;
    try {
        await loadPeerCatalog();
        lastPeerCatalogRefreshAtMs = Date.now();
    } catch (error) {
        console.error("peer catalog refresh failed", error);
    } finally {
        peerCatalogRefreshInFlight = false;
    }
}

function persistP2PRoomsToStorage() {
    writeStorageJson(roomsStorageKey(), knownP2PRooms);
}

function removeRoomMessagesFromStorage(roomId) {
    delete roomMessagesById[roomId];
    try {
        localStorage.removeItem(roomMessagesStorageKey(roomId));
    } catch (error) {
        console.error("remove room messages failed", error);
    }
}

function loadRoomMessages(roomId) {
    const safeRoomId = normalizeText(roomId);
    if (!safeRoomId) {
        return [];
    }

    if (Array.isArray(roomMessagesById[safeRoomId])) {
        return roomMessagesById[safeRoomId].slice();
    }

    const stored = readStorageJson(roomMessagesStorageKey(safeRoomId), []);
    const sanitized = [];

    for (const item of Array.isArray(stored) ? stored : []) {
        const message = normalizeText(item.message);
        if (!message) {
            continue;
        }

        const iso = normalizeText(item.iso_timestamp) || nowIso();
        sanitized.push({
            sender: normalizeText(item.sender) || "anonymous",
            sender_user: normalizeText(item.sender_user),
            message,
            iso_timestamp: iso,
            timestamp: normalizeText(item.timestamp) || formatTimestamp(iso)
        });
    }

    roomMessagesById[safeRoomId] = sanitized;
    return sanitized.slice();
}

function persistRoomMessages(roomId, messages) {
    const safeRoomId = normalizeText(roomId);
    if (!safeRoomId) {
        return;
    }

    const safeMessages = Array.isArray(messages) ? messages.slice(-P2P_MESSAGE_LIMIT) : [];
    roomMessagesById[safeRoomId] = safeMessages;
    writeStorageJson(roomMessagesStorageKey(safeRoomId), safeMessages);
}

function directRoomIdForPeer(peerId) {
    const safePeerId = normalizePeerId(peerId);
    const pair = [localPeerId, safePeerId].filter(Boolean).sort();
    return `direct::${pair.join("::")}`;
}

function peerLabelById(peerId) {
    const safePeerId = normalizePeerId(peerId);
    if (!safePeerId) {
        return "";
    }

    if (safePeerId === localPeerId || safePeerId === currentUser) {
        return currentUser || safePeerId;
    }

    const found = knownPeers.find((peer) => normalizePeerId(peer.peer_id) === safePeerId);
    if (!found) {
        return safePeerId;
    }

    return normalizeText(found.user_id) || safePeerId;
}

function peerDisplayLabelFromObject(peer) {
    const peerId = normalizePeerId(peer.peer_id);
    const userId = normalizeText(peer.user_id);

    if (!peerId && !userId) {
        return "unknown";
    }

    if (userId && peerId && userId !== peerId) {
        return `${userId} (${peerId})`;
    }

    return userId || peerId;
}

function defaultDirectRoomName(peerId) {
    const label = peerLabelById(peerId) || normalizePeerId(peerId) || "peer";
    return `Direct: ${label}`;
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

function getRoomById(roomId) {
    const safeRoomId = normalizeText(roomId);
    return knownP2PRooms.find((room) => room.room_id === safeRoomId) || null;
}

function upsertRoom(room) {
    const safeRoomId = normalizeText(room.room_id);
    if (!safeRoomId) {
        return null;
    }

    const peers = sanitizePeerIds(room.peers);
    const candidate = {
        room_id: safeRoomId,
        room_name: normalizeText(room.room_name) || (peers.length <= 1 ? defaultDirectRoomName(peers[0]) : "Private Conversation"),
        peers,
        type: normalizeText(room.type) || (peers.length <= 1 ? "direct" : "private"),
        updated_at: normalizeText(room.updated_at) || nowIso()
    };

    const index = knownP2PRooms.findIndex((item) => item.room_id === safeRoomId);
    if (index >= 0) {
        knownP2PRooms[index] = {
            ...knownP2PRooms[index],
            ...candidate,
            peers
        };
    } else {
        knownP2PRooms.push(candidate);
    }

    knownP2PRooms = sortRoomsByRecent(knownP2PRooms);
    persistP2PRoomsToStorage();
    renderP2PRoomList();

    const current = getRoomById(safeRoomId);
    if (current) {
        syncRoomPeerBindings(current);
    }
    return current;
}

function removeRoom(roomId) {
    const safeRoomId = normalizeText(roomId);
    if (!safeRoomId) {
        return;
    }

    knownP2PRooms = knownP2PRooms.filter((room) => room.room_id !== safeRoomId);
    persistP2PRoomsToStorage();
    removeRoomMessagesFromStorage(safeRoomId);

    peerConnections.forEach((state) => {
        state.roomIds.delete(safeRoomId);
    });

    renderP2PRoomList();
}

function ensureDirectRoom(peerId) {
    const safePeerId = normalizePeerId(peerId);
    if (!safePeerId) {
        return null;
    }

    const roomId = directRoomIdForPeer(safePeerId);
    const existing = getRoomById(roomId);
    if (existing) {
        return existing;
    }

    return upsertRoom({
        room_id: roomId,
        room_name: defaultDirectRoomName(safePeerId),
        peers: [safePeerId],
        type: "direct",
        updated_at: nowIso()
    });
}

function ensureRoomFromIncoming(senderPeerId, payload) {
    const safeSenderPeerId = normalizePeerId(senderPeerId);
    const payloadRoomId = normalizeText(payload.room_id);
    const payloadRoomName = normalizeText(payload.room_name);

    const payloadPeers = sanitizePeerIds(payload.peers);
    if (safeSenderPeerId && !payloadPeers.includes(safeSenderPeerId) && safeSenderPeerId !== localPeerId) {
        payloadPeers.push(safeSenderPeerId);
    }

    if (!payloadRoomId && payloadPeers.length <= 1) {
        return ensureDirectRoom(safeSenderPeerId);
    }

    const roomId = payloadRoomId || `private::${makeUuid()}`;
    const existing = getRoomById(roomId);
    if (existing) {
        const mergedPeers = sanitizePeerIds(existing.peers.concat(payloadPeers));
        return upsertRoom({
            ...existing,
            peers: mergedPeers,
            updated_at: nowIso()
        });
    }

    const peers = payloadPeers.length > 0 ? payloadPeers : [safeSenderPeerId].filter(Boolean);
    const roomName = payloadRoomName || (peers.length <= 1 ? defaultDirectRoomName(peers[0]) : buildPrivateRoomName(peers));

    return upsertRoom({
        room_id: roomId,
        room_name: roomName,
        peers,
        type: peers.length <= 1 ? "direct" : "private",
        updated_at: nowIso()
    });
}

function appendLocalP2PMessage(roomId, message) {
    const safeRoomId = normalizeText(roomId);
    if (!safeRoomId) {
        return;
    }

    const safeMessage = normalizeText(message.message);
    if (!safeMessage) {
        return;
    }

    const iso = normalizeText(message.iso_timestamp) || nowIso();
    const item = {
        sender: normalizeText(message.sender) || "anonymous",
        sender_user: normalizeText(message.sender_user),
        message: safeMessage,
        iso_timestamp: iso,
        timestamp: normalizeText(message.timestamp) || formatTimestamp(iso)
    };

    const messages = loadRoomMessages(safeRoomId);
    messages.push(item);
    persistRoomMessages(safeRoomId, messages);

    const room = getRoomById(safeRoomId);
    if (room) {
        upsertRoom({ ...room, updated_at: nowIso() });
    }
}

function sortKnownPeers(peers) {
    const copy = Array.isArray(peers) ? peers.slice() : [];
    copy.sort((left, right) => {
        const leftLabel = `${left.user_id}|${left.peer_id}`.toLowerCase();
        const rightLabel = `${right.user_id}|${right.peer_id}`.toLowerCase();
        if (leftLabel < rightLabel) {
            return -1;
        }
        if (leftLabel > rightLabel) {
            return 1;
        }
        return 0;
    });
    return copy;
}

function setKnownPeers(peers, options = {}) {
    const merge = options.merge !== false;
    const byPeerId = new Map();

    if (merge) {
        for (const peer of knownPeers) {
            const peerId = normalizePeerId(peer.peer_id);
            if (!peerId || peerId === localPeerId) {
                continue;
            }

            byPeerId.set(peerId, {
                peer_id: peerId,
                user_id: normalizeText(peer.user_id) || peerId,
                online: false
            });
        }
    }

    for (const peer of Array.isArray(peers) ? peers : []) {
        const peerId = normalizePeerId(peer.peer_id);
        if (!peerId || peerId === localPeerId) {
            continue;
        }

        const previous = byPeerId.get(peerId);
        byPeerId.set(peerId, {
            peer_id: peerId,
            user_id: normalizeText(peer.user_id) || (previous ? previous.user_id : peerId),
            online: Boolean(peer.online)
        });
    }

    knownPeers = sortKnownPeers(Array.from(byPeerId.values()));
    renderPeerSearchResults();
    renderP2PRoomList();

    if (currentTarget.mode === MODE_P2P && currentTarget.id) {
        const room = getRoomById(currentTarget.id);
        if (room) {
            const peerText = room.peers.map(peerLabelById).join(", ");
            currentTarget.subtitle = peerText ? `Peers: ${peerText}` : "Private conversation";
            document.getElementById("current-room-subtitle").textContent = currentTarget.subtitle;
        }
    }
}

function findKnownPeerExact(query) {
    const safeQuery = normalizeText(query).toLowerCase();
    if (!safeQuery) {
        return null;
    }

    return (
        knownPeers.find((peer) => {
            return (
                normalizePeerId(peer.peer_id) === safeQuery
                || normalizeText(peer.user_id).toLowerCase() === safeQuery
            );
        }) || null
    );
}

async function resolvePeerFromServer(query) {
    const safeQuery = normalizeText(query);
    if (!safeQuery) {
        return null;
    }

    const data = await apiJson("/api/peer/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: safeQuery })
    });

    const peer = data && typeof data === "object" ? data.peer : null;
    if (!peer || typeof peer !== "object") {
        return null;
    }

    const resolvedPeerId = normalizePeerId(peer.peer_id);
    if (!resolvedPeerId) {
        return null;
    }

    return {
        peer_id: resolvedPeerId,
        user_id: normalizeText(peer.user_id) || resolvedPeerId,
        online: Boolean(peer.online)
    };
}

async function maybeSearchPeersInDatabase(query, force = false) {
    const safeQuery = normalizeText(query).toLowerCase();
    if (!safeQuery) {
        return;
    }

    const nowMs = Date.now();
    if (!force) {
        if (peerDbSearchInFlight) {
            return;
        }

        if (safeQuery === lastPeerDbSearchQuery && nowMs - lastPeerDbSearchAtMs < 2000) {
            return;
        }
    }

    peerDbSearchInFlight = true;
    try {
        const data = await apiJson("/api/peers/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: safeQuery, limit: 30, online_only: false })
        });

        const peers = data && typeof data === "object" && Array.isArray(data.peers) ? data.peers : [];
        if (peers.length > 0) {
            setKnownPeers(peers, { merge: true });
        }
        lastPeerDbSearchQuery = safeQuery;
        lastPeerDbSearchAtMs = Date.now();
    } catch (error) {
        console.error("database peer search failed", error);
    } finally {
        peerDbSearchInFlight = false;
    }
}

async function tryAddPeerFromSearchInput() {
    const input = document.getElementById("peer-search-input");
    const query = normalizeText(input.value);
    if (!query) {
        return false;
    }

    const exactKnownPeer = findKnownPeerExact(query);
    if (exactKnownPeer) {
        addSelectedPeer(exactKnownPeer.peer_id);
        return true;
    }

    await refreshPeerCatalogForSearch(true);

    const refreshedKnownPeer = findKnownPeerExact(query);
    if (refreshedKnownPeer) {
        addSelectedPeer(refreshedKnownPeer.peer_id);
        return true;
    }

    const resolvedPeer = await resolvePeerFromServer(query);
    if (!resolvedPeer) {
        showToast("Peer not found in account database", true);
        return false;
    }

    setKnownPeers([resolvedPeer], { merge: true });
    addSelectedPeer(resolvedPeer.peer_id);
    return true;
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

    const text = await response.text();
    let payload = null;

    if (text) {
        try {
            payload = JSON.parse(text);
        } catch (_error) {
            payload = text;
        }
    }

    if (!response.ok) {
        const message =
            payload && typeof payload === "object"
                ? (payload.error && payload.error.message) || payload.message
                : String(payload || "");
        throw new Error(message || `Request failed: ${response.status}`);
    }

    if (payload && typeof payload === "object" && !Array.isArray(payload)) {
        if (payload.status === "error") {
            const message =
                payload.error && payload.error.message
                    ? payload.error.message
                    : payload.message || "Request failed";
            throw new Error(message);
        }
    }

    return payload;
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
    } else {
        input.placeholder = "Select a conversation to start chatting";
    }
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

    if (mode === MODE_CHANNEL && id && !Object.prototype.hasOwnProperty.call(channelSeqById, id)) {
        channelSeqById[id] = -1;
    }

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

    for (const message of Array.isArray(messages) ? messages : []) {
        const row = document.createElement("div");
        row.className = "msg";

        const time = document.createElement("span");
        time.className = "msg-time";
        time.textContent = `[${String(message.timestamp || "")}]`;

        const senderNode = document.createElement("span");
        senderNode.className = "msg-sender";

        const senderRaw = normalizeText(message.sender) || "anonymous";
        let senderLabel = senderRaw;
        if (senderRaw === localPeerId || senderRaw === currentUser || senderRaw === "me") {
            senderLabel = "me";
        } else {
            senderLabel = peerLabelById(senderRaw);
        }

        if (senderLabel === senderRaw) {
            const fallbackUser = normalizeText(message.sender_user);
            if (fallbackUser) {
                senderLabel = fallbackUser;
            }
        }

        senderNode.textContent = `${senderLabel}:`;

        row.appendChild(time);
        row.appendChild(document.createTextNode(" "));
        row.appendChild(senderNode);
        row.appendChild(document.createTextNode(" "));
        row.appendChild(document.createTextNode(String(message.message || "")));
        container.appendChild(row);
    }

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

    for (const channel of knownChannels) {
        const item = buildSidebarItem({
            label: `# ${channel}`,
            kind: "channel",
            active: currentTarget.mode === MODE_CHANNEL && currentTarget.id === channel,
            onSelect: async () => {
                setTarget(MODE_CHANNEL, channel, `# ${channel}`, "Public channel conversation");
                channelSeqById[channel] = -1;
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
                    channelSeqById[safeName] = -1;
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

                delete channelSeqById[channel];
                delete channelMessagesById[channel];

                await refreshSidebarData();
                if (wasActive) {
                    ensureActiveTarget();
                    await refreshCurrentMessages();
                }
            }
        });
        list.appendChild(item);
    }
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

    for (const room of knownP2PRooms) {
        const dynamicName =
            room.type === "direct" && room.peers.length === 1
                ? defaultDirectRoomName(room.peers[0])
                : normalizeText(room.room_name) || "Private Conversation";

        const peerText = room.peers.map(peerLabelById).join(", ");
        const item = buildSidebarItem({
            label: dynamicName,
            kind: "conversation",
            active: currentTarget.mode === MODE_P2P && currentTarget.id === room.room_id,
            onSelect: async () => {
                setTarget(
                    MODE_P2P,
                    room.room_id,
                    dynamicName,
                    peerText ? `Peers: ${peerText}` : "Private conversation"
                );
                await refreshCurrentMessages();
            },
            onRename: async () => {
                const safeName = await promptRename("conversation", dynamicName);
                if (!safeName || safeName === dynamicName) {
                    return;
                }

                upsertRoom({ ...room, room_name: safeName, updated_at: nowIso() });
                const wasActive = currentTarget.mode === MODE_P2P && currentTarget.id === room.room_id;
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
                if (!(await confirmLeave("conversation", dynamicName))) {
                    return;
                }

                const wasActive = currentTarget.mode === MODE_P2P && currentTarget.id === room.room_id;
                removeRoom(room.room_id);

                if (wasActive) {
                    ensureActiveTarget();
                    await refreshCurrentMessages();
                }
            }
        });
        list.appendChild(item);
    }
}

function renderPeerSearchResults() {
    const list = document.getElementById("p2p-peer-search-results");
    list.replaceChildren();

    if (composerMode !== COMPOSER_P2P) {
        list.classList.remove("visible");
        return;
    }

    const query = normalizeText(document.getElementById("peer-search-input").value).toLowerCase();

    const matches = knownPeers.filter((peer) => {
        const peerId = normalizePeerId(peer.peer_id);
        const userId = normalizeText(peer.user_id);
        if (!peerId || peerId === localPeerId || selectedPeerIds.includes(peerId)) {
            return false;
        }

        if (!query) {
            return Boolean(peer.online);
        }

        const matchesQuery = peerId.includes(query) || userId.toLowerCase().includes(query);
        return matchesQuery;
    });

    if (matches.length === 0) {
        if (query) {
            void maybeSearchPeersInDatabase(query, false);
        } else {
            void refreshPeerCatalogForSearch(false);
        }

        const empty = document.createElement("li");
        empty.textContent = query
            ? "No peer found. Press Enter to resolve from database."
            : "No online peers yet";
        list.appendChild(empty);
        list.classList.add("visible");
        return;
    }

    for (const peer of matches) {
        const li = document.createElement("li");
        const status = peer.online ? "[online]" : "[offline]";
        li.textContent = `${peerDisplayLabelFromObject(peer)} ${status}`;
        li.addEventListener("click", () => {
            addSelectedPeer(normalizePeerId(peer.peer_id));
        });
        list.appendChild(li);
    }

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
    const safePeerId = normalizePeerId(peerId);
    if (!safePeerId || selectedPeerIds.includes(safePeerId) || safePeerId === localPeerId) {
        return;
    }

    selectedPeerIds.push(safePeerId);
    document.getElementById("peer-search-input").value = "";
    selectedPeerExpanded = false;
    renderSelectedPeerSelection();
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
            const defaultChannel = knownChannels[0];
            setTarget(MODE_CHANNEL, defaultChannel, `# ${defaultChannel}`, "Public channel conversation");
            channelSeqById[defaultChannel] = -1;
            return;
        }

        if (knownP2PRooms.length > 0) {
            const room = knownP2PRooms[0];
            const peerText = room.peers.map(peerLabelById).join(", ");
            const title = room.type === "direct" && room.peers.length === 1
                ? defaultDirectRoomName(room.peers[0])
                : room.room_name;
            setTarget(
                MODE_P2P,
                room.room_id,
                title,
                peerText ? `Peers: ${peerText}` : "Private conversation"
            );
            return;
        }

        setTarget("", "", "No room selected", "Use + Add/Create or + New P2P from the left side.");
    }
}

async function loadChannels() {
    const data = await apiJson("/api/my-channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}"
    });

    const previousPeerId = localPeerId;

    currentUser = normalizeText(data.user);
    localPeerId = normalizePeerId(data.peer_id);
    updateAccountStrip();

    knownChannels = Array.isArray(data.channels) ? data.channels : [];

    if (localPeerId && localPeerId !== previousPeerId) {
        signalLastEventId = 0;
        channelSeqById = {};
        channelMessagesById = {};
        loadP2PRoomsFromStorage();
    }

    renderChannelList();
    renderP2PRoomList();
}

async function loadPeerCatalog() {
    const data = await apiJson("/api/online-peers", { method: "GET" });
    setKnownPeers(Array.isArray(data.peers) ? data.peers : []);
}

async function refreshSidebarData() {
    await loadChannels();
    await loadPeerCatalog();
    ensureActiveTarget();
}

async function refreshCurrentMessages() {
    if (!currentTarget.mode || !currentTarget.id) {
        renderMessages([]);
        return;
    }

    const token = latestViewToken;

    if (currentTarget.mode === MODE_CHANNEL) {
        const cached = channelMessagesById[currentTarget.id];
        renderMessages(Array.isArray(cached) ? cached : []);

        if (!Object.prototype.hasOwnProperty.call(channelSeqById, currentTarget.id)) {
            channelSeqById[currentTarget.id] = -1;
        }

        if (!Array.isArray(cached)) {
            try {
                const snapshot = await apiJson("/api/get-messages", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ channel: currentTarget.id })
                });

                if (token !== latestViewToken) {
                    return;
                }

                channelMessagesById[currentTarget.id] = Array.isArray(snapshot) ? snapshot : [];
                renderMessages(channelMessagesById[currentTarget.id]);
            } catch (error) {
                console.error("channel snapshot failed", error);
            }
        }

        return;
    }

    const messages = loadRoomMessages(currentTarget.id);
    if (token !== latestViewToken) {
        return;
    }

    renderMessages(messages);
}

function chooseRoomContextForPeer(state) {
    for (const roomId of state.roomIds) {
        const room = getRoomById(roomId);
        if (room) {
            return {
                room_id: room.room_id,
                room_name: room.room_name
            };
        }
    }

    return {
        room_id: "",
        room_name: ""
    };
}

function syncRoomPeerBindings(room) {
    if (!room || !Array.isArray(room.peers)) {
        return;
    }

    for (const peerId of room.peers) {
        const state = ensurePeerConnection(peerId, { roomId: room.room_id });
        if (state) {
            state.roomIds.add(room.room_id);
        }
    }
}

function attachDataChannel(state, channel) {
    if (!state || !channel) {
        return;
    }

    state.channel = channel;

    channel.onopen = () => {
        console.info(`p2p data channel open: ${state.peerId}`);
        flushPendingOutgoingMessages(state);
    };

    channel.onclose = () => {
        console.info(`p2p data channel closed: ${state.peerId}`);
    };

    channel.onerror = (error) => {
        console.error("p2p data channel error", error);
    };

    channel.onmessage = (event) => {
        handleIncomingP2PData(state.peerId, event.data).catch((error) => {
            console.error("p2p message handling failed", error);
        });
    };
}

function flushPendingOutgoingMessages(state) {
    if (!state || !Array.isArray(state.pendingOutgoingMessages)) {
        return;
    }

    if (!state.channel || state.channel.readyState !== "open") {
        return;
    }

    while (state.pendingOutgoingMessages.length > 0) {
        const payload = state.pendingOutgoingMessages.shift();
        try {
            state.channel.send(payload);
        } catch (error) {
            console.error("flush pending outgoing message failed", error);
            state.pendingOutgoingMessages.unshift(payload);
            break;
        }
    }
}

function shouldReplacePeerConnectionState(state) {
    if (!state || !state.pc) {
        return true;
    }

    const signalingState = state.pc.signalingState;
    const connectionState = state.pc.connectionState;
    return signalingState === "closed" || connectionState === "failed" || connectionState === "closed";
}

function closePeerConnectionState(state) {
    if (!state) {
        return;
    }

    try {
        if (state.channel && state.channel.readyState !== "closed") {
            state.channel.close();
        }
    } catch (_error) {
        // best effort cleanup
    }

    try {
        if (state.pc && state.pc.signalingState !== "closed") {
            state.pc.close();
        }
    } catch (_error) {
        // best effort cleanup
    }
}

function ensurePeerConnection(peerId, options = {}) {
    const safePeerId = normalizePeerId(peerId);
    if (!safePeerId || safePeerId === localPeerId) {
        return null;
    }

    let state = peerConnections.get(safePeerId);
    let carryRoomIds = [];
    let carryPendingOutgoing = [];

    if (state && shouldReplacePeerConnectionState(state)) {
        carryRoomIds = Array.from(state.roomIds || []);
        carryPendingOutgoing = Array.isArray(state.pendingOutgoingMessages)
            ? state.pendingOutgoingMessages.slice()
            : [];

        closePeerConnectionState(state);
        peerConnections.delete(safePeerId);
        state = null;
    }

    if (!state) {
        const pc = new RTCPeerConnection(RTC_CONFIG);
        // Perfect Negotiation: deterministic role from peer-id comparison.
        // Both ends compute opposite values so exactly one is polite.
        const polite = String(localPeerId) < String(safePeerId);
        state = {
            peerId: safePeerId,
            pc,
            channel: null,
            pendingRemoteCandidates: [],
            pendingOutgoingMessages: carryPendingOutgoing,
            roomIds: new Set(carryRoomIds),
            polite,
            makingOffer: false,
            ignoreOffer: false,
            isSettingRemoteAnswerPending: false
        };

        pc.onicecandidate = (event) => {
            if (!event.candidate) {
                return;
            }

            const roomContext = chooseRoomContextForPeer(state);
            const candidatePayload = event.candidate.toJSON ? event.candidate.toJSON() : event.candidate;

            sendSignalCandidate(
                safePeerId,
                candidatePayload,
                roomContext.room_id,
                event.candidate.sdpMid,
                event.candidate.sdpMLineIndex
            ).catch((error) => {
                console.error("send signal candidate failed", error);
            });
        };

        pc.ondatachannel = (event) => {
            attachDataChannel(state, event.channel);
        };

        pc.onnegotiationneeded = async () => {
            const roomContext = chooseRoomContextForPeer(state);
            try {
                state.makingOffer = true;
                await pc.setLocalDescription();
                await sendSignalOffer(
                    state.peerId,
                    pc.localDescription ? pc.localDescription.sdp : "",
                    roomContext.room_id,
                    roomContext.room_name
                );
            } catch (error) {
                console.error("negotiation needed failed", error);
            } finally {
                state.makingOffer = false;
            }
        };

        pc.onconnectionstatechange = () => {
            const stateName = pc.connectionState;
            if (stateName === "failed" || stateName === "closed") {
                console.warn(`p2p connection ${stateName}: ${safePeerId}`);
            } else if (stateName === "disconnected") {
                console.info(`p2p connection disconnected: ${safePeerId}`);
            }
        };

        peerConnections.set(safePeerId, state);
    }

    if (options.roomId) {
        state.roomIds.add(options.roomId);
    }

    if (options.initiate) {
        ensureChannelForPeer(state);
    }

    return state;
}

async function waitForOpenDataChannel(state, timeoutMs = 4500) {
    const started = Date.now();

    while (Date.now() - started < timeoutMs) {
        if (state && state.channel && state.channel.readyState === "open") {
            return state.channel;
        }
        await delay(120);
    }

    return null;
}

function ensureChannelForPeer(state) {
    // Create a data channel on this side if neither side has one yet.
    // Creating a data channel triggers `onnegotiationneeded`, which drives
    // the offer through the Perfect Negotiation flow.
    if (!state || !state.pc) {
        return;
    }

    if (state.channel) {
        return;
    }

    try {
        const channel = state.pc.createDataChannel("chat");
        attachDataChannel(state, channel);
    } catch (error) {
        console.error("create data channel failed", error);
    }
}

function buildIceCandidateFromPayload(payload) {
    const raw = payload ? payload.candidate : null;
    if (!raw) {
        return null;
    }

    if (typeof raw === "string") {
        return new RTCIceCandidate({
            candidate: raw,
            sdpMid: payload.sdp_mid === undefined ? null : payload.sdp_mid,
            sdpMLineIndex: payload.sdp_mline_index === undefined ? null : payload.sdp_mline_index
        });
    }

    if (typeof raw === "object") {
        return new RTCIceCandidate(raw);
    }

    return null;
}

async function flushPendingCandidates(state) {
    if (!state || state.pendingRemoteCandidates.length === 0) {
        return;
    }

    const pending = state.pendingRemoteCandidates.slice();
    state.pendingRemoteCandidates = [];

    for (const candidate of pending) {
        try {
            await state.pc.addIceCandidate(candidate);
        } catch (error) {
            console.error("add pending ice candidate failed", error);
        }
    }
}

async function postSignal(path, payload) {
    return apiJson(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
}

async function sendSignalOffer(toPeerId, sdp, roomId, roomName) {
    return postSignal("/api/signal/offer", {
        to_peer_id: toPeerId,
        sdp,
        room_id: roomId || "",
        room_name: roomName || ""
    });
}

async function sendSignalAnswer(toPeerId, sdp, roomId) {
    return postSignal("/api/signal/answer", {
        to_peer_id: toPeerId,
        sdp,
        room_id: roomId || ""
    });
}

async function sendSignalCandidate(toPeerId, candidate, roomId, sdpMid, sdpMLineIndex) {
    return postSignal("/api/signal/candidate", {
        to_peer_id: toPeerId,
        candidate,
        room_id: roomId || "",
        sdp_mid: sdpMid,
        sdp_mline_index: sdpMLineIndex
    });
}

async function sendSignalRoom(toPeerId, roomId, roomName, peers) {
    return postSignal("/api/signal/room", {
        to_peer_id: toPeerId,
        room_id: roomId || "",
        room_name: roomName || "",
        peers: Array.isArray(peers) ? peers : []
    });
}

async function handleSignalOffer(event) {
    const fromPeerId = normalizePeerId(event.from_peer_id);
    if (!fromPeerId) {
        return;
    }

    const payload = event.payload || {};
    // Preserve raw SDP (including trailing CRLF) — Chrome's parser rejects
    // SDPs whose final line lacks its CRLF terminator.
    const sdp = String(payload.sdp || "");
    if (!sdp.trim()) {
        return;
    }

    const roomId = normalizeText(payload.room_id);
    const roomName = normalizeText(payload.room_name);

    const state = ensurePeerConnection(fromPeerId, { roomId });
    if (!state) {
        return;
    }

    // Perfect Negotiation: detect glare and ignore the incoming offer
    // when this peer is impolite and is also currently making/holding
    // a local offer. The polite peer always accepts (rolls back local).
    const readyForOffer =
        !state.makingOffer &&
        (state.pc.signalingState === "stable" || state.isSettingRemoteAnswerPending);
    const offerCollision = !readyForOffer;

    state.ignoreOffer = !state.polite && offerCollision;
    if (state.ignoreOffer) {
        return;
    }

    try {
        await state.pc.setRemoteDescription(new RTCSessionDescription({ type: "offer", sdp }));
        await flushPendingCandidates(state);
        await state.pc.setLocalDescription();
        await sendSignalAnswer(
            fromPeerId,
            state.pc.localDescription ? state.pc.localDescription.sdp : "",
            roomId
        );
    } catch (error) {
        console.error("handle signal offer failed", error);
        return;
    }

    const room = ensureRoomFromIncoming(fromPeerId, {
        room_id: roomId,
        room_name: roomName,
        peers: [fromPeerId]
    });
    if (room) {
        syncRoomPeerBindings(room);
    }
}

async function handleSignalAnswer(event) {
    const fromPeerId = normalizePeerId(event.from_peer_id);
    if (!fromPeerId) {
        return;
    }

    const payload = event.payload || {};
    // Preserve raw SDP — see handleSignalOffer.
    const sdp = String(payload.sdp || "");
    if (!sdp.trim()) {
        return;
    }

    const state = ensurePeerConnection(fromPeerId, { roomId: normalizeText(payload.room_id) });
    if (!state) {
        return;
    }

    if (state.pc.signalingState !== "have-local-offer") {
        // Stale answer (e.g. we already rolled back due to glare); ignore.
        return;
    }

    state.isSettingRemoteAnswerPending = true;
    try {
        await state.pc.setRemoteDescription(new RTCSessionDescription({ type: "answer", sdp }));
    } catch (error) {
        console.error("set remote answer failed", error);
        return;
    } finally {
        state.isSettingRemoteAnswerPending = false;
    }

    await flushPendingCandidates(state);
}

async function handleSignalCandidate(event) {
    const fromPeerId = normalizePeerId(event.from_peer_id);
    if (!fromPeerId) {
        return;
    }

    const payload = event.payload || {};
    const state = ensurePeerConnection(fromPeerId, { roomId: normalizeText(payload.room_id) });
    if (!state) {
        return;
    }

    const candidate = buildIceCandidateFromPayload(payload);
    if (!candidate) {
        return;
    }

    if (!state.pc.remoteDescription || !state.pc.remoteDescription.type) {
        state.pendingRemoteCandidates.push(candidate);
        return;
    }

    try {
        await state.pc.addIceCandidate(candidate);
    } catch (error) {
        if (!state.ignoreOffer) {
            console.error("add ice candidate failed", error);
        }
    }
}

async function processSignalEvent(event) {
    const type = normalizeText(event.type).toLowerCase();

    if (type === "channel-created") {
        await handleChannelCreatedSignal(event);
        return;
    }

    if (type === "p2p-room") {
        await handleP2PRoomSignal(event);
        return;
    }

    if (type === "offer") {
        await handleSignalOffer(event);
        return;
    }

    if (type === "answer") {
        await handleSignalAnswer(event);
        return;
    }

    if (type === "channel-update") {
        await handleChannelUpdateSignal(event);
        return;
    }

    if (type === "candidate") {
        await handleSignalCandidate(event);
    }
}

async function handleChannelCreatedSignal(event) {
    const payload = event && typeof event === "object" ? event.payload : null;
    const channel = normalizeText(payload && payload.channel);
    if (!channel) {
        return;
    }

    if (!knownChannels.includes(channel)) {
        try {
            await apiJson("/api/join-channel", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ channel })
            });
        } catch (error) {
            console.error("auto-join on channel-created failed", error);
        }
    }

    await refreshSidebarData();
}

async function handleP2PRoomSignal(event) {
    const fromPeerId = normalizePeerId(event && event.from_peer_id);
    if (!fromPeerId) {
        return;
    }

    const payload = event && typeof event === "object" ? event.payload : null;
    const roomId = normalizeText(payload && payload.room_id);
    const roomName = normalizeText(payload && payload.room_name);
    const peers = Array.isArray(payload && payload.peers) ? payload.peers : [fromPeerId];

    const room = ensureRoomFromIncoming(fromPeerId, {
        room_id: roomId,
        room_name: roomName,
        peers
    });

    if (!room) {
        return;
    }

    // Don't initiate from the receiver. The room creator already calls
    // ensureChannelForPeer; if its offer is delayed or lost, glare is
    // resolved by Perfect Negotiation when the receiver later sends a
    // message and creates its own data channel.
    syncRoomPeerBindings(room);
}

async function handleChannelUpdateSignal(event) {
    const payload = event && typeof event === "object" ? event.payload : null;
    const channel = normalizeText(payload && payload.channel);
    if (!channel) {
        return;
    }

    const seqValue = Number(payload && payload.seq);
    if (Number.isFinite(seqValue)) {
        const currentSeq = Number(channelSeqById[channel]);
        const suggestedLastSeq = Math.max(-1, Math.floor(seqValue) - 1);
        if (!Number.isFinite(currentSeq) || currentSeq < suggestedLastSeq) {
            channelSeqById[channel] = suggestedLastSeq;
        }
    }

    startChannelLongPollLoop();

    if (currentTarget.mode === MODE_CHANNEL && currentTarget.id === channel) {
        delete channelMessagesById[channel];
        await refreshCurrentMessages();
    }
}

async function handleIncomingP2PData(fromPeerId, rawData) {
    let payload = null;

    try {
        payload = JSON.parse(String(rawData || ""));
    } catch (_error) {
        return;
    }

    if (!payload || normalizeText(payload.type) !== "p2p-message") {
        return;
    }

    const senderPeerId = normalizePeerId(payload.sender_peer_id) || normalizePeerId(fromPeerId);
    const messageText = normalizeText(payload.message);
    if (!senderPeerId || !messageText) {
        return;
    }

    const room = ensureRoomFromIncoming(senderPeerId, payload);
    if (!room) {
        return;
    }

    const iso = normalizeText(payload.timestamp) || nowIso();
    appendLocalP2PMessage(room.room_id, {
        sender: senderPeerId,
        sender_user: normalizeText(payload.sender_user),
        message: messageText,
        iso_timestamp: iso,
        timestamp: formatTimestamp(iso)
    });

    if (currentTarget.mode === MODE_P2P && currentTarget.id === room.room_id) {
        await refreshCurrentMessages();
    } else {
        showToast(`New P2P message from ${peerLabelById(senderPeerId)}`);
    }
}

async function sendP2PPayloadToPeer(peerId, payload, room) {
    const safePeerId = normalizePeerId(peerId);
    if (!safePeerId || safePeerId === localPeerId) {
        return false;
    }

    const state = ensurePeerConnection(safePeerId, {
        roomId: room.room_id,
        roomName: room.room_name,
        initiate: true
    });

    if (!state) {
        return false;
    }

    const serializedPayload = JSON.stringify(payload);
    if (state.channel && state.channel.readyState === "open") {
        state.channel.send(serializedPayload);
        return true;
    }

    state.pendingOutgoingMessages.push(serializedPayload);

    const channel = await waitForOpenDataChannel(state, 4500);
    if (channel) {
        flushPendingOutgoingMessages(state);
        return true;
    }

    return false;
}

async function sendP2PMessage(roomId, messageText) {
    const room = getRoomById(roomId);
    if (!room) {
        throw new Error("Conversation not found");
    }

    const iso = nowIso();
    appendLocalP2PMessage(room.room_id, {
        sender: localPeerId,
        sender_user: currentUser,
        message: messageText,
        iso_timestamp: iso,
        timestamp: formatTimestamp(iso)
    });

    if (currentTarget.mode === MODE_P2P && currentTarget.id === room.room_id) {
        renderMessages(loadRoomMessages(room.room_id));
    }

    const payload = {
        type: "p2p-message",
        room_id: room.room_id,
        room_name: room.room_name,
        peers: room.peers,
        sender_peer_id: localPeerId,
        sender_user: currentUser,
        message: messageText,
        timestamp: iso
    };

    let failed = 0;
    for (const peerId of room.peers) {
        const delivered = await sendP2PPayloadToPeer(peerId, payload, room);
        if (!delivered) {
            failed += 1;
        }
    }

    if (failed > 0) {
        showToast(`Saved locally. ${failed} peer(s) not connected.`, true);
    }
}

async function runSignalPollingLoop(token) {
    while (token === signalLoopToken) {
        try {
            const response = await postSignal("/api/signal/poll", {
                peer_id: localPeerId,
                last_event_id: signalLastEventId,
                timeout_seconds: SIGNAL_POLL_TIMEOUT_SECONDS
            });

            if (token !== signalLoopToken) {
                return;
            }

            if (typeof response.last_event_id === "number") {
                signalLastEventId = response.last_event_id;
            }

            if (Array.isArray(response.peers)) {
                setKnownPeers(response.peers);
            }

            const events = Array.isArray(response.events) ? response.events : [];
            for (const event of events) {
                await processSignalEvent(event);
            }
        } catch (error) {
            console.error("signal poll failed", error);
            await delay(RETRY_DELAY_MS);
        }
    }
}

function startSignalPollingLoop() {
    signalLoopToken += 1;
    const token = signalLoopToken;
    void runSignalPollingLoop(token);
}

async function runChannelLongPollLoop(token) {
    while (token === channelLoopToken) {
        if (currentTarget.mode !== MODE_CHANNEL || !currentTarget.id) {
            await delay(300);
            continue;
        }

        const channel = currentTarget.id;
        if (!Object.prototype.hasOwnProperty.call(channelSeqById, channel)) {
            channelSeqById[channel] = -1;
        }

        const lastSeq = channelSeqById[channel];

        try {
            const response = await apiJson("/api/channel/long-poll", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    channel,
                    last_seq: lastSeq,
                    timeout_seconds: CHANNEL_POLL_TIMEOUT_SECONDS
                })
            });

            if (token !== channelLoopToken) {
                return;
            }

            if (typeof response.seq === "number") {
                channelSeqById[channel] = response.seq;
            }

            if (response.has_update && Array.isArray(response.messages)) {
                channelMessagesById[channel] = response.messages;
                if (currentTarget.mode === MODE_CHANNEL && currentTarget.id === channel) {
                    renderMessages(response.messages);
                }
            }
        } catch (error) {
            console.error("channel long poll failed", error);
            await delay(RETRY_DELAY_MS);
        }
    }
}

function startChannelLongPollLoop() {
    channelLoopToken += 1;
    const token = channelLoopToken;
    void runChannelLongPollLoop(token);
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
            const channel = currentTarget.id;
            const response = await apiJson("/api/send-channel", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ channel, message })
            });

            const stored = response && typeof response === "object" ? response.message : null;
            if (stored && typeof stored === "object") {
                const cached = Array.isArray(channelMessagesById[channel]) ? channelMessagesById[channel].slice() : [];
                cached.push(stored);
                channelMessagesById[channel] = cached;
            } else {
                const snapshot = await apiJson("/api/get-messages", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ channel })
                });
                channelMessagesById[channel] = Array.isArray(snapshot) ? snapshot : [];
            }

            if (response && typeof response.seq === "number") {
                channelSeqById[channel] = response.seq;
            }

            if (currentTarget.mode === MODE_CHANNEL && currentTarget.id === channel) {
                renderMessages(channelMessagesById[channel]);
            }

            startChannelLongPollLoop();
        } else {
            await sendP2PMessage(currentTarget.id, message);
        }

        input.value = "";
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
    channelSeqById[safeChannel] = -1;
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

function createOrReuseP2PRoomFromPeers(peers) {
    const cleanPeers = sanitizePeerIds(peers);
    if (cleanPeers.length === 0) {
        return null;
    }

    if (cleanPeers.length === 1) {
        return ensureDirectRoom(cleanPeers[0]);
    }

    return upsertRoom({
        room_id: `private::${makeUuid()}`,
        room_name: buildPrivateRoomName(cleanPeers),
        peers: cleanPeers,
        type: "private",
        updated_at: nowIso()
    });
}

async function createP2PRoomFromComposer() {
    let peers = selectedPeerIds.slice();
    if (peers.length === 0) {
        const added = await tryAddPeerFromSearchInput();
        if (added) {
            peers = selectedPeerIds.slice();
        }

        if (peers.length === 0) {
            showToast("Add at least one peer ID", true);
            return;
        }
    }

    const room = createOrReuseP2PRoomFromPeers(peers);
    if (!room) {
        showToast("Unable to create conversation", true);
        return;
    }

    selectedPeerIds = [];
    selectedPeerExpanded = false;
    document.getElementById("peer-search-input").value = "";
    renderSelectedPeerSelection();
    renderPeerSearchResults();

    const peerText = room.peers.map(peerLabelById).join(", ");
    const title = room.type === "direct" && room.peers.length === 1
        ? defaultDirectRoomName(room.peers[0])
        : room.room_name;

    setTarget(
        MODE_P2P,
        room.room_id,
        title,
        peerText ? `Peers: ${peerText}` : "Private conversation"
    );

    syncRoomPeerBindings(room);

    let failedOffers = 0;

    for (const peerId of room.peers) {
        try {
            await sendSignalRoom(peerId, room.room_id, room.room_name, room.peers);
        } catch (error) {
            console.error("send room signal failed", error);
        }

        const state = ensurePeerConnection(peerId, {
            roomId: room.room_id,
            roomName: room.room_name,
            initiate: true
        });

        if (!state) {
            failedOffers += 1;
        }
    }

    if (failedOffers > 0) {
        showToast("Room created. Retrying peer connection in background.", true);
    }

    await refreshCurrentMessages();
}

async function logout() {
    try {
        signalLoopToken += 1;
        channelLoopToken += 1;
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
        if (event.key !== "Enter" || event.repeat) {
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
        void refreshPeerCatalogForSearch(true);
    });

    document.getElementById("peer-search-input").addEventListener("input", () => {
        renderPeerSearchResults();
        const query = normalizeText(document.getElementById("peer-search-input").value);
        if (query) {
            void maybeSearchPeersInDatabase(query, false);
        }
    });

    document.getElementById("peer-search-input").addEventListener("keydown", (event) => {
        if (event.key !== "Enter" || event.repeat) {
            return;
        }

        event.preventDefault();
        tryAddPeerFromSearchInput().catch((error) => {
            showToast(error.message || "Unable to resolve peer ID", true);
        });
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
        startSignalPollingLoop();
        startChannelLongPollLoop();
    } catch (error) {
        showToast(error.message || "Initialization failed", true);
    }
}

window.addEventListener("load", initialize);
