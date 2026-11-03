(() => {
  "use strict";
  const PARENT_ORIGIN = "*"; // Parent is the internal SMA origin; messages are validated by source and type.
  const pending = new Map();
  let requestSeq = 0;
  let loaded = false;
  let hasSnapshot = false;
  let readyTimer = null;
  let lastSnapshotUrl = "";
  let lastSnapshotHtml = "";

  window.__JMA_SOURCE = { url: "", title: "", html: "", capturedAt: "", doc: null };
  window.__JMA_EXTENSION_READY__ = Promise.resolve({ hostedMode: true });
  const cfg = window.JORMALL_SMA_HOSTED_CONFIG || {};
  window.JORMALL_SMA_OVERLAY_CONFIG = {
    apiBaseUrl: String(cfg.apiBaseUrl || window.location.origin).replace(/\/$/, ""),
    logoUrl: cfg.logoUrl || "",
    hostedMode: true,
    extensionMode: false,
    extensionEnabled: true
  };

  function notifyParent(message) {
    if (window.parent !== window) window.parent.postMessage(message, PARENT_ORIGIN);
  }

  window.JORMALL_SMA_HOST_BRIDGE = {
    getSource: () => window.__JMA_SOURCE,
    fetchSmaText: (url) => new Promise((resolve, reject) => {
      const requestId = `jma-${Date.now()}-${++requestSeq}`;
      pending.set(requestId, { resolve, reject, timer: setTimeout(() => {
        pending.delete(requestId);
        reject(new Error("Timed out while reading the SMA page."));
      }, 15000) });
      notifyParent({ type: "JMA_FETCH_SMA", requestId, url: String(url || "") });
    }),
    requestSnapshot: () => notifyParent({ type: "JMA_REQUEST_SNAPSHOT" }),
    setFrameState: (state) => notifyParent({ type: "JMA_FRAME_STATE", state })
  };

  window.JORMALL_SMA_EXTENSION_BRIDGE = {
    fetch: (url, options = {}) => new Promise((resolve, reject) => {
      const requestId = `jma-api-${Date.now()}-${++requestSeq}`;
      const timeoutMs = /\/health(?:\?|$)/.test(String(url || "")) ? 12000 : 190000;
      pending.set(requestId, { kind: "api", resolve, reject, timer: setTimeout(() => {
        pending.delete(requestId);
        reject(new Error("The SMA AI request timed out."));
      }, timeoutMs) });
      notifyParent({
        type: "JMA_FETCH_API",
        requestId,
        url: String(url || ""),
        options: {
          method: String(options.method || "GET"),
          headers: options.headers || {},
          body: options.body == null ? null : String(options.body)
        }
      });
    })
  };

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = () => reject(new Error(`Failed to load ${src}`));
      document.head.appendChild(s);
    });
  }

  async function ensureLoaded() {
    if (loaded) return;
    loaded = true;
    document.getElementById("jma-host-loading")?.remove();
    await loadScript("parser.js");
    await loadScript("overlay.js");
  }

  function applySnapshot(snapshot) {
    if (!snapshot || typeof snapshot.html !== "string") return;
    const nextUrl = String(snapshot.url || "");
    if (hasSnapshot && nextUrl === lastSnapshotUrl && snapshot.html === lastSnapshotHtml) return;
    lastSnapshotUrl = nextUrl;
    lastSnapshotHtml = snapshot.html;
    hasSnapshot = true;
    if (readyTimer) clearInterval(readyTimer);
    const parser = new DOMParser();
    window.__JMA_SOURCE = {
      url: nextUrl,
      title: String(snapshot.title || ""),
      html: snapshot.html,
      capturedAt: String(snapshot.capturedAt || ""),
      doc: parser.parseFromString(snapshot.html, "text/html")
    };
    if (window.JorMallSMAParser?.__setSource) window.JorMallSMAParser.__setSource(window.__JMA_SOURCE);
    if (typeof window.JorMallSMAHostedRefresh === "function") window.JorMallSMAHostedRefresh();
  }

  window.addEventListener("message", async (event) => {
    if (event.source !== window.parent) return;
    const message = event.data || {};
    if (message.type === "JMA_SMA_SNAPSHOT") {
      applySnapshot(message.snapshot);
      try { await ensureLoaded(); }
      catch (error) {
        document.body.innerHTML = `<div style="font-family:Arial;padding:18px;color:#b42318"><strong>SMA Assistant failed to load.</strong><br>${String(error.message || error)}</div>`;
      }
      return;
    }
    if (message.type === "JMA_FETCH_SMA_RESULT") {
      const item = pending.get(String(message.requestId || ""));
      if (!item) return;
      clearTimeout(item.timer); pending.delete(String(message.requestId || ""));
      if (message.response?.success) item.resolve(message.response.payload);
      else item.reject(new Error(message.response?.error || "SMA fetch failed."));
      return;
    }
    if (message.type === "JMA_FETCH_API_RESULT") {
      const item = pending.get(String(message.requestId || ""));
      if (!item || item.kind !== "api") return;
      clearTimeout(item.timer); pending.delete(String(message.requestId || ""));
      if (!message.response?.success) {
        item.reject(new Error(message.response?.error || "SMA AI request failed."));
        return;
      }
      const payload = message.response.payload || {};
      const body = String(payload.body || "");
      item.resolve({
        ok: Boolean(payload.ok),
        status: Number(payload.status || 0),
        statusText: String(payload.statusText || ""),
        url: String(payload.url || ""),
        headers: { get: name => String(name || "").toLowerCase() === "content-type" ? String(payload.contentType || "") : null },
        text: async () => body,
        json: async () => JSON.parse(body)
      });
    }
  });

  if (window.parent === window) {
    const loading = document.getElementById("jma-host-loading");
    if (loading) loading.textContent = "Open this assistant from inside your SMA page (http://sma/).";
  } else {
    notifyParent({ type: "JMA_HOST_READY" });
    readyTimer = setInterval(() => {
      if (hasSnapshot) return clearInterval(readyTimer);
      notifyParent({ type: "JMA_HOST_READY" });
    }, 1000);
  }
})();
