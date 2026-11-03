(() => {
  "use strict";

  if (window.__JMA_HOSTED_BRIDGE_LOADED__) return;
  window.__JMA_HOSTED_BRIDGE_LOADED__ = true;

  const HOSTED_ORIGIN = "https://jormallapp.com";
  const HOSTED_APP_URL = `${HOSTED_ORIGIN}/sma/extension-csv-test/index.html`;
  const EXTENSION_SHARED_KEY = "REDACTED_CONFIGURE_LOCALLY";
  const FRAME_ID = "jormall-sma-hosted-frame";
  const OPEN_WIDTH = "min(760px, 96vw)";
  const CLOSED_WIDTH = "128px";

  let frame;
  let snapshotTimer = null;
  let lastSnapshotSignature = "";

  function createFrame() {
    if (document.getElementById(FRAME_ID)) return document.getElementById(FRAME_ID);
    frame = document.createElement("iframe");
    frame.id = FRAME_ID;
    frame.src = `${HOSTED_APP_URL}?bridge=2&ts=${Date.now()}`;
    frame.title = "JorMall SMA Assistant";
    frame.setAttribute("allow", "clipboard-write");
    Object.assign(frame.style, {
      position: "fixed",
      top: "0",
      right: "0",
      width: CLOSED_WIDTH,
      height: "100vh",
      border: "0",
      margin: "0",
      padding: "0",
      zIndex: "2147483646",
      background: "transparent",
      colorScheme: "light",
      transition: "width 160ms ease",
      boxShadow: "none"
    });
    document.documentElement.appendChild(frame);
    return frame;
  }

  function pageSnapshot() {
    return {
      url: window.location.href,
      title: document.title || "",
      html: document.documentElement?.outerHTML || "",
      capturedAt: new Date().toISOString()
    };
  }

  function sendSnapshot(force = false) {
    frame = frame || createFrame();
    if (!frame?.contentWindow) return;
    const snapshot = pageSnapshot();
    const signature = `${snapshot.url}|${snapshot.title}|${snapshot.html.length}|${snapshot.html.slice(-500)}`;
    if (!force && signature === lastSnapshotSignature) return;
    lastSnapshotSignature = signature;
    frame.contentWindow.postMessage({
      type: "JMA_SMA_SNAPSHOT",
      snapshot,
      extensionSharedKey: EXTENSION_SHARED_KEY
    }, HOSTED_ORIGIN);
  }

  function scheduleSnapshot() {
    clearTimeout(snapshotTimer);
    snapshotTimer = setTimeout(() => sendSnapshot(false), 140);
  }

  window.addEventListener("message", async (event) => {
    if (event.origin !== HOSTED_ORIGIN || event.source !== frame?.contentWindow) return;
    const message = event.data || {};

    if (message.type === "JMA_HOST_READY" || message.type === "JMA_REQUEST_SNAPSHOT") {
      sendSnapshot(true);
      return;
    }

    if (message.type === "JMA_FRAME_STATE") {
      if (message.state === "open") {
        frame.style.display = "block";
        frame.style.width = OPEN_WIDTH;
        frame.style.boxShadow = "-8px 0 30px rgba(0,0,0,.16)";
      } else if (message.state === "unsupported") {
        frame.style.display = "none";
      } else {
        frame.style.display = "block";
        frame.style.width = CLOSED_WIDTH;
        frame.style.boxShadow = "none";
      }
      return;
    }

    if (message.type === "JMA_FETCH_SMA") {
      const requestId = String(message.requestId || "");
      try {
        const response = await chrome.runtime.sendMessage({ type: "JMA_FETCH_SMA_PAGE", url: String(message.url || "") });
        frame.contentWindow.postMessage({ type: "JMA_FETCH_SMA_RESULT", requestId, response }, HOSTED_ORIGIN);
      } catch (error) {
        frame.contentWindow.postMessage({ type: "JMA_FETCH_SMA_RESULT", requestId, response: { success: false, error: error?.message || String(error) } }, HOSTED_ORIGIN);
      }
      return;
    }

    if (message.type === "JMA_FETCH_API") {
      const requestId = String(message.requestId || "");
      try {
        const response = await chrome.runtime.sendMessage({
          type: "JMA_FETCH_API",
          url: String(message.url || ""),
          options: message.options || {}
        });
        frame.contentWindow.postMessage({ type: "JMA_FETCH_API_RESULT", requestId, response }, HOSTED_ORIGIN);
      } catch (error) {
        frame.contentWindow.postMessage({ type: "JMA_FETCH_API_RESULT", requestId, response: { success: false, error: error?.message || String(error) } }, HOSTED_ORIGIN);
      }
    }
  });

  createFrame();

  const observer = new MutationObserver(scheduleSnapshot);
  observer.observe(document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true });

  window.addEventListener("load", () => sendSnapshot(true), { once: true });
  window.addEventListener("pageshow", () => sendSnapshot(true));
  setInterval(() => sendSnapshot(false), 1200);
})();
