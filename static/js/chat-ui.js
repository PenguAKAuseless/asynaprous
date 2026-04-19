let currentChannel = "general";
let localMessageCount = 0;

async function loadChannels() {
    // using async: fetch(): network request - need data from BE
    const res = await fetch("/api/channels");               // async --> await - wait response from BE before proceeding
    const channels = await res.json();
    const list = document.getElementById("channel-list");   // get channel list element
    channels.forEach(c => {                                 
        let li = document.createElement("li");
        li.textContent = "# " + c;
        li.onclick = () => selectChannel(c);
        list.appendChild(li);
    });
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
    const res = await fetch("/api/get-messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel: currentChannel })
    });
    const messages = await res.json();
    
    if (messages.length > localMessageCount) {
        if (localMessageCount !== 0) {
            console.log("New message notification triggered!");
        }
        localMessageCount = messages.length;
        renderMessages(messages);
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
    container.innerHTML = "";
    messages.forEach(m => {
        let div = document.createElement("div");
        div.className = "msg";
        div.innerHTML = `<span class="msg-time">[${m.timestamp}]</span> 
                         <span class="msg-sender">${m.sender}:</span> ${m.message}`;
        container.appendChild(div);
    });
    container.scrollTop = container.scrollHeight;
}
/*
    find id of message which is ready to show
    clear old messages - avoid duplicate
    loop: create a new <div> for each message and append it to the container
    scroll to bottom - always show the latest message
*/
async function sendMessage() {
    const input = document.getElementById("msg-input");
    const msg = input.value.trim();
    if (!msg) return;

    await fetch("/api/send-channel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel: currentChannel, message: msg, sender: "me" })
    });
    
    input.value = "";
    pollMessages(); // Fetch immediately after sending
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