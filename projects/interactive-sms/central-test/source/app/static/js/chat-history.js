(function () {
    "use strict";

    const config = window.CHAT_HISTORY_CONFIG || {};
    const basePath = (config.appBasePath || "").replace(/\/$/, "");
    const csrfToken = document.querySelector('meta[name="chat-history-csrf"]')?.content || "";
    const state = {
        page: 1,
        pageSize: 25,
        total: 0,
        selectedId: "",
        selectedConversation: null,
        debounceTimer: null,
    };

    const elements = {
        tableBody: document.getElementById("conversation-table-body"),
        emptyState: document.getElementById("empty-state"),
        status: document.getElementById("dashboard-status"),
        pageStatus: document.getElementById("page-status"),
        previousPage: document.getElementById("previous-page"),
        nextPage: document.getElementById("next-page"),
        exportButton: document.getElementById("export-button"),
        detailEmpty: document.getElementById("detail-empty"),
        detailContent: document.getElementById("detail-content"),
        detailCustomer: document.getElementById("detail-customer"),
        detailMeta: document.getElementById("detail-meta"),
        detailMobile: document.getElementById("detail-mobile"),
        detailCampaign: document.getElementById("detail-campaign"),
        detailStarted: document.getElementById("detail-started"),
        detailLast: document.getElementById("detail-last"),
        detailStatus: document.getElementById("detail-status"),
        detailAssigned: document.getElementById("detail-assigned"),
        detailFollowUp: document.getElementById("detail-follow-up"),
        detailNotes: document.getElementById("detail-notes"),
        saveManagement: document.getElementById("save-management"),
        archiveButton: document.getElementById("archive-button"),
        restoreButton: document.getElementById("restore-button"),
        refreshDetail: document.getElementById("refresh-detail"),
        messageList: document.getElementById("message-list"),
        search: document.getElementById("conversation-search"),
        statusFilter: document.getElementById("status-filter"),
        languageFilter: document.getElementById("language-filter"),
        followUpFilter: document.getElementById("follow-up-filter"),
        campaignFilter: document.getElementById("campaign-filter"),
        assignedFilter: document.getElementById("assigned-filter"),
        dateFromFilter: document.getElementById("date-from-filter"),
        dateToFilter: document.getElementById("date-to-filter"),
    };

    function apiUrl(path, params) {
        const url = new URL(`${basePath}${path}`, window.location.origin);
        Object.entries(params || {}).forEach(([key, value]) => {
            if (value !== undefined && value !== null && String(value) !== "") {
                url.searchParams.set(key, String(value));
            }
        });
        return url;
    }

    function setStatus(message, tone) {
        elements.status.textContent = "";
        if (!message) {
            return;
        }
        const node = document.createElement("span");
        if (tone) {
            node.dataset.tone = tone;
        }
        node.textContent = message;
        elements.status.appendChild(node);
    }

    function filters(includePage) {
        const params = {
            search: elements.search.value.trim(),
            campaign: elements.campaignFilter.value.trim(),
            status: elements.statusFilter.value,
            assigned_employee: elements.assignedFilter.value.trim(),
            language: elements.languageFilter.value,
            follow_up: elements.followUpFilter.value,
            date_from: elements.dateFromFilter.value,
            date_to: elements.dateToFilter.value,
        };
        if (includePage) {
            params.page = state.page;
            params.page_size = state.pageSize;
        }
        return params;
    }

    function textCell(row, value) {
        const cell = document.createElement("td");
        cell.textContent = value || "";
        row.appendChild(cell);
        return cell;
    }

    function formatDate(row, dateKey, timeKey) {
        const date = row[dateKey] || "";
        const time = row[timeKey] || "";
        return [date, time].filter(Boolean).join(" ");
    }

    function renderConversations(rows) {
        elements.tableBody.textContent = "";
        elements.emptyState.hidden = rows.length > 0;

        rows.forEach((conversation) => {
            const row = document.createElement("tr");
            row.className = "conversation-row";
            if (conversation.id === state.selectedId) {
                row.classList.add("selected");
            }

            const customerCell = document.createElement("td");
            const customerButton = document.createElement("button");
            customerButton.type = "button";
            customerButton.className = "row-button";
            if (conversation.id === state.selectedId) {
                customerButton.classList.add("active");
            }
            customerButton.textContent = conversation.customer_name || "Unknown customer";
            customerButton.addEventListener("click", () => loadConversationDetail(conversation.id));
            customerCell.appendChild(customerButton);
            row.appendChild(customerCell);

            textCell(row, conversation.customer_mobile);
            textCell(row, conversation.campaign_name || conversation.chatbot_name);
            textCell(row, formatDate(conversation, "last_activity_date", "last_activity_time"));
            textCell(row, conversation.message_count);
            textCell(row, (conversation.language || "").toUpperCase());

            const statusCell = document.createElement("td");
            const statusPill = document.createElement("span");
            statusPill.className = "status-pill";
            statusPill.textContent = (conversation.status || "").replace(/_/g, " ");
            statusCell.appendChild(statusPill);
            row.appendChild(statusCell);

            const followCell = document.createElement("td");
            const followPill = document.createElement("span");
            followPill.className = conversation.follow_up_required ? "follow-pill required" : "follow-pill";
            followPill.textContent = conversation.follow_up_required ? "Required" : "No";
            followCell.appendChild(followPill);
            row.appendChild(followCell);

            textCell(row, conversation.assigned_employee);
            row.addEventListener("dblclick", () => loadConversationDetail(conversation.id));
            elements.tableBody.appendChild(row);
        });
    }

    function updatePagination() {
        const totalPages = Math.max(1, Math.ceil(state.total / state.pageSize));
        elements.pageStatus.textContent = `Page ${state.page} of ${totalPages} (${state.total} conversations)`;
        elements.previousPage.disabled = state.page <= 1;
        elements.nextPage.disabled = state.page >= totalPages;
    }

    async function fetchJson(url, options) {
        const response = await fetch(url, {
            credentials: "same-origin",
            ...options,
        });
        if (!response.ok) {
            throw new Error("Request failed.");
        }
        return response.json();
    }

    async function loadConversations() {
        setStatus("Loading conversations...");
        try {
            const payload = await sendJson(
                "/api/admin/conversations/search",
                "POST",
                filters(true)
            );
            state.total = payload.total || 0;
            renderConversations(payload.conversations || []);
            updatePagination();
            setStatus("");
        } catch (error) {
            setStatus("Unable to load conversations.", "error");
        }
    }

    function messageLanguage(content, fallback) {
        if (fallback === "ar" || /[\u0600-\u06FF]/.test(content || "")) {
            return "ar";
        }
        return "en";
    }

    function renderMessages(messages, fallbackLanguage) {
        elements.messageList.textContent = "";
        messages.forEach((message) => {
            const item = document.createElement("article");
            item.className = `history-message ${message.role || "assistant"}`;

            const meta = document.createElement("div");
            meta.className = "message-meta";
            const role = document.createElement("span");
            role.textContent = message.role === "user" ? "Customer" : "Assistant";
            const time = document.createElement("time");
            time.dateTime = message.created_at || "";
            time.textContent = [message.created_date, message.created_time].filter(Boolean).join(" ");
            meta.append(role, time);

            const content = document.createElement("p");
            const lang = messageLanguage(message.content, fallbackLanguage);
            content.className = `message-content lang-${lang}`;
            content.dir = lang === "ar" ? "rtl" : "ltr";
            content.textContent = message.content || "";

            item.append(meta, content);
            elements.messageList.appendChild(item);
        });
    }

    function fillDetail(conversation, messages) {
        state.selectedConversation = conversation;
        elements.detailEmpty.hidden = true;
        elements.detailContent.hidden = false;
        elements.detailCustomer.textContent = conversation.customer_name || "Unknown customer";
        elements.detailMeta.textContent = conversation.conversation_id;
        elements.detailMobile.textContent = conversation.customer_mobile || "";
        elements.detailCampaign.textContent = conversation.campaign_name || conversation.chatbot_name || "";
        elements.detailStarted.textContent = formatDate(conversation, "started_date", "started_time");
        elements.detailLast.textContent = formatDate(conversation, "last_activity_date", "last_activity_time");
        elements.detailStatus.value = conversation.status || "open";
        elements.detailAssigned.value = conversation.assigned_employee || "";
        elements.detailFollowUp.checked = Boolean(conversation.follow_up_required);
        elements.detailNotes.value = conversation.internal_notes || "";
        elements.archiveButton.hidden = conversation.status === "archived";
        elements.restoreButton.hidden = conversation.status !== "archived";
        renderMessages(messages || [], conversation.language);
    }

    async function loadConversationDetail(id) {
        if (!id) {
            return;
        }
        state.selectedId = id;
        setStatus("Loading conversation...");
        try {
            const payload = await fetchJson(apiUrl(`/api/admin/conversations/${id}`));
            fillDetail(payload.conversation, payload.messages);
            await loadConversations();
            setStatus("");
        } catch (error) {
            setStatus("Unable to load conversation.", "error");
        }
    }

    async function sendJson(path, method, body) {
        return fetchJson(apiUrl(path), {
            method,
            headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": csrfToken,
            },
            body: JSON.stringify(body || {}),
        });
    }

    async function downloadExport() {
        setStatus("Preparing export...");
        try {
            const response = await fetch(apiUrl("/api/admin/conversations/export.csv"), {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRF-Token": csrfToken,
                },
                body: JSON.stringify(filters(false)),
            });
            if (!response.ok) {
                throw new Error("Export failed.");
            }
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = "chat_conversations.csv";
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
            setStatus("Export downloaded.", "success");
        } catch (error) {
            setStatus("Unable to export conversations.", "error");
        }
    }

    async function saveManagementFields() {
        const id = state.selectedId;
        if (!id) {
            return;
        }
        setStatus("Saving changes...");
        try {
            await sendJson(`/api/admin/conversations/${id}/status`, "PATCH", {
                status: elements.detailStatus.value,
            });
            await sendJson(`/api/admin/conversations/${id}/assignment`, "PATCH", {
                assigned_employee: elements.detailAssigned.value,
            });
            await sendJson(`/api/admin/conversations/${id}/follow-up`, "PATCH", {
                follow_up_required: elements.detailFollowUp.checked,
            });
            await sendJson(`/api/admin/conversations/${id}/notes`, "PATCH", {
                internal_notes: elements.detailNotes.value,
            });
            await loadConversationDetail(id);
            setStatus("Changes saved.", "success");
        } catch (error) {
            setStatus("Unable to save changes.", "error");
        }
    }

    async function setArchived(archived) {
        const id = state.selectedId;
        if (!id) {
            return;
        }
        setStatus(archived ? "Archiving conversation..." : "Restoring conversation...");
        try {
            await sendJson(`/api/admin/conversations/${id}/${archived ? "archive" : "restore"}`, "POST");
            await loadConversationDetail(id);
            setStatus(archived ? "Conversation archived." : "Conversation restored.", "success");
        } catch (error) {
            setStatus("Unable to update archive status.", "error");
        }
    }

    function scheduleReload() {
        window.clearTimeout(state.debounceTimer);
        state.debounceTimer = window.setTimeout(() => {
            state.page = 1;
            loadConversations();
        }, 250);
    }

    function bindEvents() {
        [
            elements.search,
            elements.campaignFilter,
            elements.assignedFilter,
            elements.dateFromFilter,
            elements.dateToFilter,
        ].forEach((input) => input.addEventListener("input", scheduleReload));
        [
            elements.statusFilter,
            elements.languageFilter,
            elements.followUpFilter,
        ].forEach((input) => input.addEventListener("change", scheduleReload));

        elements.previousPage.addEventListener("click", () => {
            state.page = Math.max(1, state.page - 1);
            loadConversations();
        });
        elements.nextPage.addEventListener("click", () => {
            state.page += 1;
            loadConversations();
        });
        elements.exportButton.addEventListener("click", downloadExport);
        elements.saveManagement.addEventListener("click", saveManagementFields);
        elements.archiveButton.addEventListener("click", () => setArchived(true));
        elements.restoreButton.addEventListener("click", () => setArchived(false));
        elements.refreshDetail.addEventListener("click", () => loadConversationDetail(state.selectedId));
    }

    bindEvents();
    loadConversations();
})();
