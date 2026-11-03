(function () {
    "use strict";

    var script = document.currentScript;
    if (!script) {
        return;
    }

    var clientSlug = String(script.getAttribute("data-client-slug") || "").trim();
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(clientSlug)) {
        console.warn("JorMall chatbot widget: missing or invalid data-client-slug.");
        return;
    }

    var registry = window.__JORMALL_CHATBOT_WIDGETS__ || {};
    window.__JORMALL_CHATBOT_WIDGETS__ = registry;
    if (registry[clientSlug]) {
        return;
    }
    registry[clientSlug] = true;

    var scriptUrl = new URL(script.src, window.location.href);
    var baseUrl = scriptUrl.origin;
    var iframeOrigin = new URL(baseUrl).origin;
    var position = String(script.getAttribute("data-position") || "right").toLowerCase() === "left"
        ? "left"
        : "right";
    var launcherLabel = String(script.getAttribute("data-launcher-label") || "Open chat");
    var bottomOffset = cssSize(script.getAttribute("data-bottom-offset") || "24px");
    var sideOffset = cssSize(script.getAttribute("data-side-offset") || "24px");
    var parentOrigin = /^https?:\/\//.test(window.location.origin)
        ? window.location.origin
        : "";
    var storageKey = "jormall_chatbot_embed_session_" + clientSlug + "_v1";
    var sessionId = loadSessionId(storageKey);

    var fallbackConfig = {
        client_slug: clientSlug,
        assistant_name: "Chat Assistant",
        company_name: "this company",
        logo_url: "",
        primary_color: "#2575b6",
        secondary_color: "#47c6f3",
        button_color: "#2575b6",
        background_color: "#ffffff"
    };

    loadConfig()
        .catch(function () {
            return fallbackConfig;
        })
        .then(createWidget);

    function cssSize(value) {
        var cleaned = String(value || "").trim();
        return /^-?\d+(\.\d+)?(px|rem|em|vh|vw|%)$/.test(cleaned)
            ? cleaned
            : "24px";
    }

    function loadSessionId(key) {
        try {
            var existing = window.localStorage.getItem(key);
            if (existing) {
                return existing;
            }
            var next = window.crypto && window.crypto.randomUUID
                ? window.crypto.randomUUID()
                : "session-" + Date.now() + "-" + Math.random().toString(16).slice(2);
            window.localStorage.setItem(key, next);
            return next;
        } catch (error) {
            return "session-" + Date.now() + "-" + Math.random().toString(16).slice(2);
        }
    }

    function loadConfig() {
        return fetch(baseUrl + "/embed/" + encodeURIComponent(clientSlug) + "/config", {
            credentials: "omit",
            mode: "cors",
            headers: {
                Accept: "application/json"
            }
        }).then(function (response) {
            if (!response.ok) {
                throw new Error("Widget config unavailable.");
            }
            return response.json();
        }).then(function (config) {
            return Object.assign({}, fallbackConfig, config || {});
        });
    }

    function createWidget(config) {
        var root = document.createElement("div");
        root.id = "jmcw-root-" + clientSlug;
        root.className = "jmcw-root jmcw-" + position;
        root.style.setProperty("--jmcw-bottom", bottomOffset);
        root.style.setProperty("--jmcw-side", sideOffset);
        root.style.setProperty("--jmcw-primary", config.button_color || config.primary_color || "#2575b6");
        root.style.setProperty("--jmcw-secondary", config.secondary_color || "#47c6f3");
        root.style.setProperty("--jmcw-bg", config.background_color || "#ffffff");

        var style = document.createElement("style");
        style.textContent = widgetCss();

        var launcher = document.createElement("button");
        launcher.type = "button";
        launcher.className = "jmcw-launcher";
        launcher.setAttribute("aria-label", launcherLabel);
        launcher.setAttribute("aria-expanded", "false");
        launcher.innerHTML = avatarMarkup(config);

        var panel = document.createElement("section");
        panel.className = "jmcw-panel";
        panel.setAttribute("aria-label", config.assistant_name || "Chat assistant");
        panel.hidden = true;

        var header = document.createElement("div");
        header.className = "jmcw-header";
        header.innerHTML =
            '<div class="jmcw-title-wrap">' +
            avatarMarkup(config) +
            '<div><strong class="jmcw-title"></strong><span class="jmcw-subtitle"></span></div>' +
            '</div>';
        header.querySelector(".jmcw-title").textContent = config.assistant_name || "Chat Assistant";
        header.querySelector(".jmcw-subtitle").textContent = config.company_name || "Company knowledge";

        var closeButton = document.createElement("button");
        closeButton.type = "button";
        closeButton.className = "jmcw-close";
        closeButton.setAttribute("aria-label", "Close chat");
        closeButton.textContent = "x";
        header.appendChild(closeButton);

        var iframe = document.createElement("iframe");
        iframe.className = "jmcw-frame";
        iframe.title = (config.assistant_name || "Chat assistant") + " chat";
        iframe.loading = "lazy";
        iframe.referrerPolicy = "strict-origin-when-cross-origin";
        iframe.sandbox = "allow-scripts allow-forms allow-same-origin allow-popups allow-popups-to-escape-sandbox";
        iframe.src = buildIframeUrl();

        panel.appendChild(header);
        panel.appendChild(iframe);
        root.appendChild(style);
        root.appendChild(panel);
        root.appendChild(launcher);
        document.body.appendChild(root);

        launcher.addEventListener("click", openPanel);
        closeButton.addEventListener("click", closePanel);
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && !panel.hidden) {
                closePanel();
                launcher.focus();
            }
        });
        window.addEventListener("message", function (event) {
            var data = event.data;
            if (event.origin !== iframeOrigin || !data || data.source !== "jormall-chatbot") {
                return;
            }
            if (data.clientSlug !== clientSlug) {
                return;
            }
            if (data.type === "close") {
                closePanel();
                launcher.focus();
            }
        });

        function openPanel() {
            panel.hidden = false;
            launcher.hidden = true;
            launcher.setAttribute("aria-expanded", "true");
            setTimeout(function () {
                iframe.focus();
            }, 0);
        }

        function closePanel() {
            panel.hidden = true;
            launcher.hidden = false;
            launcher.setAttribute("aria-expanded", "false");
        }

        function buildIframeUrl() {
            var configuredUrl = config.embed_url || "";
            var url = new URL(
                configuredUrl || baseUrl + (script.getAttribute("data-base-path") || "/sms-service-chatbot").replace(/\/+$/, "") + "?embed=1",
                baseUrl
            );
            url.searchParams.set("embed", "1");
            url.searchParams.set("session_id", sessionId);
            if (parentOrigin) {
                url.searchParams.set("parent_origin", parentOrigin);
            }
            return url.toString();
        }
    }

    function avatarMarkup(config) {
        var logoUrl = config.logo_url || config.favicon_url || "";
        if (logoUrl) {
            var absoluteLogo = new URL(logoUrl, baseUrl).toString();
            return '<span class="jmcw-avatar"><img src="' + escapeAttribute(absoluteLogo) + '" alt=""></span>';
        }
        return '<span class="jmcw-avatar jmcw-avatar-fallback" aria-hidden="true">?</span>';
    }

    function escapeAttribute(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/"/g, "&quot;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");
    }

    function widgetCss() {
        return [
            ".jmcw-root{position:fixed;bottom:calc(var(--jmcw-bottom) + env(safe-area-inset-bottom,0px));z-index:2147483000;font-family:Inter,Arial,sans-serif;color:#172033;line-height:1.4}",
            ".jmcw-right{right:calc(var(--jmcw-side) + env(safe-area-inset-right,0px))}.jmcw-left{left:calc(var(--jmcw-side) + env(safe-area-inset-left,0px))}",
            ".jmcw-root *{box-sizing:border-box}.jmcw-launcher{width:64px;height:64px;border:0;border-radius:999px;background:var(--jmcw-primary);box-shadow:0 18px 40px rgba(37,117,182,.28);cursor:pointer;display:grid;place-items:center;transition:transform .18s ease,box-shadow .18s ease}.jmcw-launcher:hover{transform:translateY(-2px);box-shadow:0 22px 48px rgba(37,117,182,.34)}.jmcw-launcher:focus-visible,.jmcw-close:focus-visible{outline:3px solid var(--jmcw-secondary);outline-offset:3px}",
            ".jmcw-avatar{width:42px;height:42px;border-radius:999px;background:#fff;display:grid;place-items:center;overflow:hidden;box-shadow:inset 0 0 0 1px rgba(180,180,180,.4);color:var(--jmcw-primary);font-weight:800}.jmcw-avatar img{width:100%;height:100%;object-fit:contain;background:transparent}.jmcw-avatar-fallback{font-size:22px}",
            ".jmcw-panel{width:min(390px,calc(100vw - 32px));height:min(680px,calc(100vh - 96px));border-radius:20px;overflow:hidden;background:var(--jmcw-bg);box-shadow:0 24px 70px rgba(20,39,68,.28);border:1px solid rgba(180,180,180,.5);display:flex;flex-direction:column}.jmcw-panel[hidden]{display:none}",
            ".jmcw-header{min-height:72px;padding:14px 14px 14px 16px;background:linear-gradient(135deg,var(--jmcw-primary),var(--jmcw-secondary));color:#fff;display:flex;align-items:center;justify-content:space-between;gap:12px}.jmcw-title-wrap{min-width:0;display:flex;align-items:center;gap:12px}.jmcw-title-wrap .jmcw-avatar{width:44px;height:44px;flex:0 0 auto}.jmcw-title{display:block;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:245px}.jmcw-subtitle{display:block;font-size:12px;opacity:.88;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:245px}.jmcw-close{width:36px;height:36px;border:1px solid rgba(255,255,255,.5);border-radius:999px;background:rgba(255,255,255,.16);color:#fff;font-size:20px;line-height:1;cursor:pointer}",
            ".jmcw-frame{width:100%;height:100%;border:0;display:block;background:#fff;flex:1 1 auto}",
            "@media (max-width:600px){.jmcw-root{left:16px;right:16px;bottom:calc(16px + env(safe-area-inset-bottom,0px))}.jmcw-launcher{margin-left:auto}.jmcw-left .jmcw-launcher{margin-left:0;margin-right:auto}.jmcw-panel{width:calc(100vw - 32px);height:min(680px,calc(100vh - 48px));border-radius:18px}.jmcw-title,.jmcw-subtitle{max-width:calc(100vw - 155px)}}"
        ].join("");
    }
})();
