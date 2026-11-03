const csrfToken =
    document.querySelector('meta[name="chat-history-csrf"]')?.content || "";
const dashboardBasePath = String(window.DASHBOARD_BASE_PATH || "").replace(/\/+$/, "");

const elements = {
    search: document.getElementById("history-search"),
    status: document.getElementById("history-status"),
    archive: document.getElementById("history-archive"),
    date: document.getElementById("history-date"),
    exportButton: document.getElementById("history-export"),
    statusLine: document.getElementById("history-status-line"),
    list: document.getElementById("conversation-list"),
    detail: document.getElementById("conversation-detail")
};

let conversations = [];
let selectedConversationId = "";
let loadTimer = null;

function dashboardUrl(path) {
    return `${dashboardBasePath}${path.startsWith("/") ? path : `/${path}`}`;
}

function setStatus(message, tone = "") {
    elements.statusLine.textContent = message || "";
    elements.statusLine.dataset.tone = tone;
}

function query() {
    const params = new URLSearchParams();
    params.set("search", elements.search.value || "");
    params.set("status", elements.status.value || "all");
    params.set("archived", elements.archive.value || "active");
    params.set("date_range", elements.date.value || "all");
    return params;
}

function text(value, fallback = "Not provided") {
    const clean = String(value || "").trim();
    return clean || fallback;
}

function conversationTitle(conversation) {
    return text(
        conversation.customer_name ||
            conversation.customer_phone ||
            conversation.session_id,
        "Anonymous conversation"
    );
}

function renderConversationList() {
    elements.list.innerHTML = "";
    if (!conversations.length) {
        const empty = document.createElement("p");
        empty.className = "empty-state";
        empty.textContent = "No conversations found.";
        elements.list.appendChild(empty);
        return;
    }

    for (const conversation of conversations) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "conversation-row";
        button.classList.toggle("active", conversation.id === selectedConversationId);
        button.addEventListener("click", () => loadConversation(conversation.id));

        const title = document.createElement("strong");
        title.textContent = conversationTitle(conversation);
        const meta = document.createElement("span");
        meta.textContent = `${conversation.last_message_date} ${conversation.last_message_time} · ${conversation.status}`;
        const detail = document.createElement("small");
        detail.textContent = text(conversation.assignee, "Unassigned");

        button.appendChild(title);
        button.appendChild(meta);
        button.appendChild(detail);
        elements.list.appendChild(button);
    }
}

function messageCard(message) {
    const article = document.createElement("article");
    article.className = `history-message ${message.role === "user" ? "user" : "assistant"}`;
    const role = document.createElement("strong");
    role.textContent = message.role === "user" ? "Customer" : "Assistant";
    const body = document.createElement("p");
    body.textContent = message.content;
    article.appendChild(role);
    article.appendChild(body);
    return article;
}

function detailField(label, value) {
    const wrapper = document.createElement("div");
    wrapper.className = "detail-field";
    const key = document.createElement("span");
    key.textContent = label;
    const val = document.createElement("strong");
    val.textContent = text(value);
    wrapper.appendChild(key);
    wrapper.appendChild(val);
    return wrapper;
}

function renderDetail(payload) {
    const conversation = payload.conversation;
    selectedConversationId = conversation.id;
    renderConversationList();
    elements.detail.innerHTML = "";

    const header = document.createElement("header");
    header.className = "detail-header";
    const title = document.createElement("h2");
    title.textContent = conversationTitle(conversation);
    const subtitle = document.createElement("p");
    subtitle.textContent = `Session ${conversation.session_id}`;
    header.appendChild(title);
    header.appendChild(subtitle);
    elements.detail.appendChild(header);

    const fields = document.createElement("section");
    fields.className = "detail-grid";
    fields.appendChild(detailField("Mobile", conversation.customer_phone));
    fields.appendChild(detailField("Company", conversation.customer_company));
    fields.appendChild(detailField("Last Message", `${conversation.last_message_date} ${conversation.last_message_time}`));
    fields.appendChild(detailField("Follow Up", conversation.follow_up_status));
    elements.detail.appendChild(fields);

    const form = document.createElement("form");
    form.className = "detail-form";
    form.innerHTML = `
        <label>Status
            <select name="status">
                <option value="open">Open</option>
                <option value="pending">Pending</option>
                <option value="resolved">Resolved</option>
            </select>
        </label>
        <label>Follow-up
            <input name="follow_up_status" type="text" maxlength="40">
        </label>
        <label>Assignee
            <input name="assignee" type="text" maxlength="120">
        </label>
        <label>Internal notes
            <textarea name="notes" rows="4" maxlength="2000"></textarea>
        </label>
        <div class="detail-actions">
            <button type="submit">Save</button>
            <button type="button" data-action="${conversation.archived ? "restore" : "archive"}">
                ${conversation.archived ? "Restore" : "Archive"}
            </button>
        </div>
    `;
    form.elements.status.value = conversation.status || "open";
    form.elements.follow_up_status.value = conversation.follow_up_status || "";
    form.elements.assignee.value = conversation.assignee || "";
    form.elements.notes.value = conversation.notes || "";
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        saveConversation(conversation.id, form);
    });
    form.querySelector("[data-action]").addEventListener("click", () => {
        toggleArchive(conversation.id, conversation.archived ? "restore" : "archive");
    });
    elements.detail.appendChild(form);

    const messages = document.createElement("section");
    messages.className = "message-list";
    for (const message of payload.messages || []) {
        messages.appendChild(messageCard(message));
    }
    elements.detail.appendChild(messages);
}

async function loadConversations() {
    setStatus("Loading conversations...");
    try {
        const response = await fetch(
            dashboardUrl(`/api/admin/chat-history/conversations?${query().toString()}`),
            { credentials: "same-origin" }
        );
        if (!response.ok) throw new Error("Could not load conversations.");
        const payload = await response.json();
        conversations = Array.isArray(payload.conversations) ? payload.conversations : [];
        renderConversationList();
        setStatus("");
    } catch (error) {
        setStatus(error.message || "Could not load conversations.", "error");
    }
}

async function loadConversation(id) {
    setStatus("Loading conversation...");
    try {
        const response = await fetch(
            dashboardUrl(`/api/admin/chat-history/conversations/${encodeURIComponent(id)}`),
            { credentials: "same-origin" }
        );
        if (!response.ok) throw new Error("Could not open conversation.");
        renderDetail(await response.json());
        setStatus("");
    } catch (error) {
        setStatus(error.message || "Could not open conversation.", "error");
    }
}

async function saveConversation(id, form) {
    const payload = {
        status: form.elements.status.value,
        follow_up_status: form.elements.follow_up_status.value,
        assignee: form.elements.assignee.value,
        notes: form.elements.notes.value
    };
    setStatus("Saving...");
    try {
        const response = await fetch(
            dashboardUrl(`/api/admin/chat-history/conversations/${encodeURIComponent(id)}/update`),
            {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": csrfToken
                },
                body: JSON.stringify(payload)
            }
        );
        if (!response.ok) throw new Error("Could not save conversation.");
        setStatus("Saved.", "success");
        await loadConversations();
        await loadConversation(id);
    } catch (error) {
        setStatus(error.message || "Could not save conversation.", "error");
    }
}

async function toggleArchive(id, action) {
    setStatus(action === "archive" ? "Archiving..." : "Restoring...");
    try {
        const response = await fetch(
            dashboardUrl(`/api/admin/chat-history/conversations/${encodeURIComponent(id)}/${action}`),
            {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "X-CSRF-Token": csrfToken
                }
            }
        );
        if (!response.ok) throw new Error("Could not update archive state.");
        selectedConversationId = "";
        elements.detail.innerHTML = '<p class="empty-state">Select a conversation.</p>';
        await loadConversations();
        setStatus("Updated.", "success");
    } catch (error) {
        setStatus(error.message || "Could not update archive state.", "error");
    }
}

function scheduleLoad() {
    clearTimeout(loadTimer);
    loadTimer = setTimeout(loadConversations, 180);
}

function exportCsv() {
    window.location.href = dashboardUrl(`/api/admin/chat-history/export.csv?${query().toString()}`);
}

elements.search.addEventListener("input", scheduleLoad);
elements.status.addEventListener("change", loadConversations);
elements.archive.addEventListener("change", loadConversations);
elements.date.addEventListener("change", loadConversations);
elements.exportButton.addEventListener("click", exportCsv);

loadConversations();
