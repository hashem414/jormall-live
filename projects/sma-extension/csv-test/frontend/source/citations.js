(() => {
  "use strict";

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, character => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    })[character]);
  }

  function sourceLabel(source) {
    if (source?.label) return String(source.label);
    if (source?.type === "sma_page") return "Current SMA page";
    const filename = String(source?.filename || "Document");
    const section = String(source?.section || "");
    return section ? `${filename} — ${section}` : filename;
  }

  function render(data) {
    const sources = Array.isArray(data?.sources) ? data.sources.filter(source => source && typeof source === "object") : [];
    const documentSources = sources.filter(source => source.type === "document");
    const retrievalStatus = String(data?.retrieval?.status || "unknown");
    const cards = sources.map(source => {
      const type = source.type === "sma_page" ? "page" : "document";
      const excerpt = String(source.excerpt || "").trim();
      const page = source.page == null || source.page === "" ? "" : ` · Page ${escapeHtml(source.page)}`;
      return `<div class="jma-source jma-source-${type}">
        <span class="jma-source-kind">${type === "page" ? "LIVE" : "DOCUMENT"}</span>
        <strong>${escapeHtml(sourceLabel(source))}${page}</strong>
        ${excerpt ? `<p>${escapeHtml(excerpt)}</p>` : ""}
      </div>`;
    }).join("\n");

    let documentNote = "";
    if (!documentSources.length) {
      documentNote = retrievalStatus === "unavailable"
        ? `<div class="jma-source-note warn">Document retrieval unavailable. This answer did not use document evidence.</div>`
        : `<div class="jma-source-note">No document evidence used.</div>`;
    }
    return `<div class="jma-sources"><div class="jma-sources-title">Sources</div>${cards}${documentNote}</div>`;
  }

  function renderMetadata(data) {
    const mode = String(data?.mode || "openai");
    const modeRow = `<div class="jma-kv"><span>Mode</span><strong>${escapeHtml(mode)}</strong></div>`;
    if (mode === "documents" || !data?.report) return modeRow;
    return `${modeRow}
      <div class="jma-kv"><span>Scope</span><strong>${escapeHtml(data.report.scope || "current")}</strong></div>
      <div class="jma-kv"><span>Companies analyzed</span><strong>${escapeHtml(data.report.companiesAnalyzed ?? "-")}</strong></div>`;
  }

  window.JorMallSMASources = Object.freeze({ render, renderMetadata, escapeHtml, sourceLabel });
})();
