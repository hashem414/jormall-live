"use strict";

const HOSTED_ORIGIN = "https://jormallapp.com";
const HOSTED_APP_URL = `${HOSTED_ORIGIN}/sma/extension-csv-test/index.html`;
const API_PREFIX = `${HOSTED_ORIGIN}/sma/extension-csv-test/api/`;
const EXTENSION_SHARED_KEY = "REDACTED_CONFIGURE_LOCALLY";
const SMA_HOSTS = new Set(["sma", "192.168.192.52"]);

function isAllowedSmaUrl(value) {
  try {
    const url = new URL(String(value || ""));
    return ["http:", "https:"].includes(url.protocol) && SMA_HOSTS.has(url.hostname.toLowerCase());
  } catch (_) {
    return false;
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({ hostedAppUrl: HOSTED_APP_URL });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "JMA_FETCH_SMA_PAGE") {
    (async () => {
      if (!isAllowedSmaUrl(message.url)) throw new Error("Blocked non-SMA URL.");
      const response = await fetch(message.url, {
        method: "GET",
        credentials: "include",
        cache: "no-store",
        redirect: "follow"
      });
      return {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText,
        url: response.url,
        body: await response.text()
      };
    })().then(payload => sendResponse({ success: true, payload }))
      .catch(error => sendResponse({ success: false, error: error?.message || String(error) }));
    return true;
  }

  if (message?.type === "JMA_FETCH_API") {
    (async () => {
      const url = String(message.url || "");
      if (!url.startsWith(API_PREFIX)) throw new Error("Blocked non-test API URL.");
      const options = message.options || {};
      const headers = new Headers(options.headers || {});
      headers.set("X-SMA-Extension-Key", EXTENSION_SHARED_KEY);
      const response = await fetch(url, {
        method: String(options.method || "GET"),
        headers,
        body: options.body == null || String(options.method || "GET").toUpperCase() === "GET" ? undefined : String(options.body),
        cache: "no-store",
        credentials: "omit",
        redirect: "follow"
      });
      return {
        ok: response.ok,
        status: response.status,
        statusText: response.statusText,
        url: response.url,
        contentType: response.headers.get("content-type") || "",
        body: await response.text()
      };
    })().then(payload => sendResponse({ success: true, payload }))
      .catch(error => sendResponse({ success: false, error: error?.message || String(error) }));
    return true;
  }

  if (message?.type === "JMA_GET_BRIDGE_INFO") {
    sendResponse({
      success: true,
      version: chrome.runtime.getManifest().version,
      hostedAppUrl: HOSTED_APP_URL
    });
    return false;
  }
});
