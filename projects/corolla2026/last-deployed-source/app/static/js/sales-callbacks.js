const csrfToken =
    document.querySelector('meta[name="sales-callback-csrf"]')?.content || "";
const dashboardBasePath = String(window.DASHBOARD_BASE_PATH || "").replace(/\/+$/, "");

function dashboardUrl(path) {
    return `${dashboardBasePath}${path.startsWith("/") ? path : `/${path}`}`;
}

const elements = {
    search: document.getElementById("callback-search"),
    statusFilter: document.getElementById("status-filter"),
    dateFilter: document.getElementById("date-filter"),
    exportButton: document.getElementById("export-button"),
    tableBody: document.getElementById("callback-table-body"),
    cardList: document.getElementById("callback-card-list"),
    emptyState: document.getElementById("empty-state"),
    status: document.getElementById("dashboard-status")
};

const labels = {
    en: {
        title: "Sales Callback Requests",
        subtitle: "Customers who asked to be contacted by the sales team.",
        logout: "Logout",
        search: "Search",
        statusFilter: "Status",
        dateFilter: "Date",
        pending: "Pending",
        contacted: "Contacted",
        all: "All",
        allDates: "All dates",
        today: "Today",
        last7: "Last 7 days",
        export: "Export CSV",
        name: "Customer Name",
        phone: "Mobile Number",
        requestDate: "Request Date",
        requestTime: "Request Time",
        status: "Status",
        actions: "Actions",
        call: "Call",
        copy: "Copy Number",
        markContacted: "Mark as Contacted",
        copied: "Number copied",
        marked: "The request has been marked as contacted.",
        empty: "No pending callback requests.",
        loading: "Loading callback requests...",
        loadError: "Could not load callback requests.",
        updateError: "Could not update the request.",
        searchPlaceholder: "Name or mobile number"
    },
    ar: {
        title: "طلبات الاتصال من فريق المبيعات",
        subtitle: "العملاء الذين طلبوا التواصل معهم من قبل فريق المبيعات.",
        logout: "تسجيل الخروج",
        search: "بحث",
        statusFilter: "الحالة",
        dateFilter: "التاريخ",
        pending: "بانتظار التواصل",
        contacted: "تم التواصل",
        all: "الكل",
        allDates: "كل التواريخ",
        today: "اليوم",
        last7: "آخر 7 أيام",
        export: "تصدير",
        name: "الاسم",
        phone: "رقم الهاتف",
        requestDate: "تاريخ الطلب",
        requestTime: "وقت الطلب",
        status: "الحالة",
        actions: "الإجراءات",
        call: "اتصال",
        copy: "نسخ الرقم",
        markContacted: "تم التواصل",
        copied: "تم نسخ الرقم",
        marked: "تم تحديث الطلب إلى تم التواصل.",
        empty: "لا توجد طلبات اتصال معلقة.",
        loading: "جارٍ تحميل طلبات الاتصال...",
        loadError: "تعذر تحميل طلبات الاتصال.",
        updateError: "تعذر تحديث الطلب.",
        searchPlaceholder: "الاسم أو رقم الهاتف"
    }
};

let currentLanguage = "en";
let currentRequests = [];
let loadTimer = null;

function text(key) {
    return labels[currentLanguage][key] || labels.en[key] || key;
}

function statusLabel(status) {
    return status === "contacted" ? text("contacted") : text("pending");
}

function setStatus(message, tone = "") {
    elements.status.textContent = message || "";
    elements.status.dataset.tone = tone;
}

function requestQuery() {
    const params = new URLSearchParams();
    params.set("status", elements.statusFilter.value || "pending");
    params.set("search", elements.search.value || "");
    params.set("date_range", elements.dateFilter.value || "all");
    return params;
}

function buildButton(label, className) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    return button;
}

function createActions(request) {
    const wrapper = document.createElement("div");
    wrapper.className = "request-actions";

    const call = document.createElement("a");
    call.className = "action-link call-link";
    call.href = `tel:${request.phone}`;
    call.textContent = text("call");
    wrapper.appendChild(call);

    const copy = buildButton(text("copy"), "action-button copy-button");
    copy.addEventListener("click", async () => {
        await navigator.clipboard.writeText(request.phone);
        setStatus(text("copied"), "success");
    });
    wrapper.appendChild(copy);

    if (request.status === "pending") {
        const contacted = buildButton(text("markContacted"), "action-button contacted-button");
        contacted.addEventListener("click", () => markContacted(request.id, contacted));
        wrapper.appendChild(contacted);
    }

    return wrapper;
}

function renderTableRow(request) {
    const row = document.createElement("tr");

    for (const value of [
        request.name,
        request.phone,
        request.request_date,
        request.request_time,
        statusLabel(request.status)
    ]) {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.appendChild(cell);
    }

    const actionsCell = document.createElement("td");
    actionsCell.appendChild(createActions(request));
    row.appendChild(actionsCell);

    return row;
}

function cardField(label, value) {
    const field = document.createElement("div");
    field.className = "card-field";

    const key = document.createElement("span");
    key.className = "card-label";
    key.textContent = label;

    const val = document.createElement("strong");
    val.textContent = value;

    field.appendChild(key);
    field.appendChild(val);
    return field;
}

function renderCard(request) {
    const card = document.createElement("article");
    card.className = "callback-card";
    card.appendChild(cardField(text("name"), request.name));
    card.appendChild(cardField(text("phone"), request.phone));
    card.appendChild(cardField(text("requestTime"), `${request.request_date} ${request.request_time}`));
    card.appendChild(cardField(text("status"), statusLabel(request.status)));
    card.appendChild(createActions(request));
    return card;
}

function renderRequests() {
    elements.tableBody.innerHTML = "";
    elements.cardList.innerHTML = "";

    for (const request of currentRequests) {
        elements.tableBody.appendChild(renderTableRow(request));
        elements.cardList.appendChild(renderCard(request));
    }

    elements.emptyState.hidden = currentRequests.length !== 0;
}

async function loadRequests() {
    setStatus(text("loading"));
    try {
        const response = await fetch(
            dashboardUrl(`/api/admin/sales-callback-dashboard/requests?${requestQuery().toString()}`),
            { credentials: "same-origin" }
        );
        if (!response.ok) {
            throw new Error(text("loadError"));
        }
        const payload = await response.json();
        currentRequests = Array.isArray(payload.requests) ? payload.requests : [];
        renderRequests();
        setStatus("");
    } catch (error) {
        setStatus(error.message || text("loadError"), "error");
    }
}

async function markContacted(requestId, button) {
    button.disabled = true;
    try {
        const response = await fetch(
            dashboardUrl(`/api/admin/sales-callback-requests/${encodeURIComponent(requestId)}/contacted`),
            {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "X-CSRF-Token": csrfToken
                }
            }
        );
        if (!response.ok) {
            throw new Error(text("updateError"));
        }
        setStatus(text("marked"), "success");
        await loadRequests();
    } catch (error) {
        button.disabled = false;
        setStatus(error.message || text("updateError"), "error");
    }
}

function scheduleLoad() {
    clearTimeout(loadTimer);
    loadTimer = setTimeout(loadRequests, 180);
}

function exportCsv() {
    window.location.href =
        dashboardUrl(`/api/admin/sales-callback-dashboard/export.csv?${requestQuery().toString()}`);
}

function updateLanguage(language) {
    currentLanguage = language;
    document.documentElement.lang = language;
    document.documentElement.dir = language === "ar" ? "rtl" : "ltr";

    document.querySelectorAll("[data-i18n]").forEach((element) => {
        const key = element.dataset.i18n;
        element.textContent = text(key);
    });

    elements.search.placeholder = text("searchPlaceholder");
    document.querySelectorAll(".language-button").forEach((button) => {
        button.classList.toggle("active", button.dataset.language === language);
    });
    renderRequests();
}

elements.search.addEventListener("input", scheduleLoad);
elements.statusFilter.addEventListener("change", loadRequests);
elements.dateFilter.addEventListener("change", loadRequests);
elements.exportButton.addEventListener("click", exportCsv);

document.querySelectorAll(".language-button").forEach((button) => {
    button.addEventListener("click", () => updateLanguage(button.dataset.language));
});

updateLanguage("en");
loadRequests();
