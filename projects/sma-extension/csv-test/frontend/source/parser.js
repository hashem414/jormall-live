(function () {
  const ALLOWED_LINK_LABELS = [
    "Transactions",
    "Request Meeting",
    "SMS Customer Delivery By Month",
    "Notes"
  ];


  let SOURCE = window.__JMA_SOURCE || { url: "", title: "", html: "", doc: null };
  function getSourceDocument() {
    return SOURCE?.doc || new DOMParser().parseFromString(SOURCE?.html || "<html><body></body></html>", "text/html");
  }
  function getSourceUrl() { return String(SOURCE?.url || ""); }
  function getSourceTitle() { return String(SOURCE?.title || getSourceDocument().title || ""); }
  function setSource(next) { SOURCE = next || SOURCE; }

  function cleanText(value) {
    return (value || "").replace(/\s+/g, " ").trim();
  }

  function firstNumber(value) {
    const match = cleanText(value).match(/-?\d[\d,]*(?:\.\d+)?/);
    return match ? match[0] : "";
  }

  function absoluteUrl(href) {
    try { return new URL(href, getSourceUrl()).href; } catch { return href || ""; }
  }

  function getPageInfo() {
    return {
      title: getSourceTitle() || "",
      url: getSourceUrl(),
      generatedAt: new Date().toISOString(),
      pageTextSample: cleanText(getSourceDocument().body.textContent).slice(0, 500)
    };
  }

  function getSummaryStats() {
    const tables = [...getSourceDocument().querySelectorAll("table")];
    const summaries = [];
    for (const table of tables) {
      const headers = [...table.querySelectorAll("thead th")].map(th => cleanText(th.textContent));
      if (headers.includes("Monthly Target") && headers.includes("SMS Delivery")) {
        const row = table.querySelector("tbody tr");
        const cells = row ? [...row.children].map(td => cleanText(td.textContent)) : [];
        summaries.push(Object.fromEntries(headers.map((h, i) => [h, cells[i] || ""])));
      }
    }
    // Keep backward compatibility with the UI: return the first summary table.
    // Company-level calculations do NOT depend on this; they are calculated from all company tables.
    return summaries[0] || {};
  }

  function isCompanyReportTable(table) {
    const headerText = cleanText([...table.querySelectorAll("thead th")].map(th => th.textContent).join(" ")).toUpperCase();
    const tableText = cleanText(table.textContent).toUpperCase();

    const hasCompanyHeaders =
      headerText.includes("COMPANY NAME") &&
      headerText.includes("SMS") &&
      headerText.includes("TARGET") &&
      headerText.includes("YTD SALES");

    const hasCompanyRows =
      !!table.querySelector("tbody tr td:first-child a[href*='makesearch']") ||
      !!table.querySelector("tbody tr td:first-child a[href*='cid=']");

    const excludesSummaryTables =
      !headerText.includes("MONTHLY TARGET") &&
      !headerText.includes("LINKS") &&
      !tableText.includes("REPORT DEFINITIONS");

    return hasCompanyHeaders && hasCompanyRows && excludesSummaryTables;
  }

  function findCompaniesTables() {
    return [...getSourceDocument().querySelectorAll("table")].filter(isCompanyReportTable);
  }

  function extractCompanyId(row) {
    const anchor = row.querySelector('a[href*="cid="], a[href*="compid="]');
    const href = anchor ? absoluteUrl(anchor.getAttribute("href")) : "";
    const match = href.match(/[?&](?:cid|compid)=(\d+)/i);
    return match ? match[1] : "";
  }

  function cacheKeyForRow(row, fallbackName = "") {
    const id = extractCompanyId(row);
    if (id) return `id:${id}`;
    const firstAnchor = row.querySelector("td:first-child a[href*='makesearch']") || row.querySelector("td:first-child a[href*='cid=']") || row.querySelector("td:first-child a");
    return `name:${cleanText(firstAnchor ? firstAnchor.textContent : fallbackName).toLowerCase()}`;
  }

  function getCachedRisks(key) {
    const cache = window.__JMA_RISK_FLAG_CACHE || {};
    return Array.isArray(cache[key]) ? cache[key] : [];
  }

  function extractLinks(row) {
    const links = [];
    row.querySelectorAll("a").forEach(a => {
      const label = cleanText(a.textContent) || (a.querySelector("img") ? "Notes" : "");
      const href = absoluteUrl(a.getAttribute("href"));
      const isApproved = ALLOWED_LINK_LABELS.some(allowed => label.toLowerCase().includes(allowed.toLowerCase()))
        || /noteslistviewallocate|briefpersone|requestmeeting|customerdeliverybymonthreport|ActiveOrderReport/i.test(href);
      if (href && isApproved) links.push({ label, href });
    });
    return links;
  }

  function getRiskFlags(row) {
    const text = cleanText(row.textContent).toUpperCase();
    const risks = [];
    if (text.includes("ATT")) risks.push("ATT");
    if (text.includes("B T") || text.includes("BT")) risks.push("BT");
    if (text.includes("SLOW SENT")) risks.push("Slow Sent");
    if (text.includes("TO CALL") || /\bCALL\b/.test(text)) risks.push("To Call");
    return [...new Set(risks)];
  }

  function parseBalances(text) {
    const ob = (text.match(/OB\s*([\d,]+)/i) || [])[1] || "";
    const pb = (text.match(/PB\s*([\d,]+)/i) || [])[1] || "";
    return { obBalance: ob, pbBalance: pb };
  }

  function isRedNode(node) {
    if (!node) return false;
    const attrColor = String(node.getAttribute && (node.getAttribute("color") || node.getAttribute("style") || "")).toLowerCase();
    if (/ca0000|ff0000|red|rgb\(\s*202\s*,\s*0\s*,\s*0\s*\)/.test(attrColor)) return true;
    try {
      const color = window.getComputedStyle(node).color.replace(/\s+/g, "").toLowerCase();
      return color === "rgb(202,0,0)" || color === "rgb(255,0,0)" || color === "red";
    } catch { return false; }
  }

  function balanceExpiredFromCell(cell) {
    if (!cell) return false;
    return [...cell.querySelectorAll("font, span, p, strong, a")].some(node => isRedNode(node) && /OB|PB|ATT|expired/i.test(cleanText(node.textContent || cell.textContent)));
  }

  function extractCompanyRows() {
    const tables = findCompaniesTables();
    if (!tables.length) return [];

    const rows = [];
    const seen = new Set();

    tables.forEach((table, tableIndex) => {
      [...table.querySelectorAll("tbody tr")]
        .filter(row => row.children.length >= 8)
        .forEach((row) => {
          const cells = [...row.children].map(td => cleanText(td.textContent));
          const firstAnchor = row.querySelector("td:first-child a[href*='makesearch']") || row.querySelector("td:first-child a[href*='cid=']") || row.querySelector("td:first-child a");
          const companyName = cleanText(firstAnchor ? firstAnchor.textContent : cells[0]);
          if (!companyName) return;

          const balances = parseBalances(cells[1] || "");
          const companyId = extractCompanyId(row);

          const record = {
            tableIndex,
            rowIndex: rows.length,
            companyId,
            companyName,
            obBalance: balances.obBalance,
            pbBalance: balances.pbBalance,
            // On salesassignedsmsuserrep.cfm this cell is the Expiry Date. Keep orderType for backward compatibility.
            expiryDate: (cells[2] || "").match(/\d{2}\/\d{2}\/\d{4}/)?.[0] || cells[2] || "",
            orderType: cells[2] || "",
            smsTargetDelivery: firstNumber(cells[3]),
            smsDeliveryThisMonth: firstNumber(cells[4]),
            forwardBooking: firstNumber(cells[5]),
            thisMonthSales: firstNumber(cells[6]),
            ytdSales: firstNumber(cells[7]),
            // The SMA cell also contains the next-year target link/text. Keep only the current-year target.
            yearlyTarget: firstNumber(cells[8]),
            lastNoteDate: (cells[9] || "").match(/\d{2}\/\d{2}\/\d{4}/)?.[0] || "",
            risks: [...new Set([...getRiskFlags(row), ...getCachedRisks(cacheKeyForRow(row, companyName))])],
            balanceExpired: balanceExpiredFromCell(row.children[1]),
            approvedLinks: extractLinks(row)
          };

          // Prevent accidental duplicate counting when the same SMA table/row is repeated in the DOM.
          // Different rows for the same company with different metrics are still kept, because the instruction is to calculate across ALL tables currently loaded.
          const duplicateKey = [
            record.companyId || record.companyName,
            record.obBalance,
            record.pbBalance,
            record.smsTargetDelivery,
            record.smsDeliveryThisMonth,
            record.thisMonthSales,
            record.ytdSales,
            record.yearlyTarget
          ].join("|");

          if (seen.has(duplicateKey)) return;
          seen.add(duplicateKey);
          rows.push(record);
        });
    });

    return rows;
  }



  function extractInlineCompanyId(row) {
    const onclickText = [...row.querySelectorAll("a")].map(a => a.getAttribute("onclick") || "").join(" ");
    const onclickMatch = onclickText.match(/(?:ActiveOrderFrm|menueHistory|menue2)\((\d+)/i);
    if (onclickMatch) return onclickMatch[1];
    return extractCompanyId(row);
  }

  function cacheKeyForInlineRow(row, fallbackName = "") {
    const id = extractInlineCompanyId(row);
    if (id) return `id:${id}`;
    return `name:${cleanText(fallbackName).toLowerCase()}`;
  }

  function parseDeliveryBreakdown(text) {
    const raw = cleanText(text);
    const ld = (raw.match(/LD\s*\(?\s*([\d,]+)/i) || [])[1] || "";
    const pd = (raw.match(/PD\s*\(?\s*([\d,]+)/i) || [])[1] || "";
    const td = (raw.match(/TD\s*\(?\s*([\d,]+)/i) || [])[1] || firstNumber(raw);
    return { localDelivery: ld, platformDelivery: pd, totalDelivery: td };
  }

  function isCategoryMonthlySummaryTable(table) {
    const headerText = cleanText([...table.querySelectorAll("thead th")].map(th => th.textContent).join(" ")).toUpperCase();
    return headerText.includes("SE") && headerText.includes("ORDER BAL") && headerText.includes("PLATFORM BAL") && headerText.includes("DELIVERY TODATE") && !headerText.includes("CUSTOMER");
  }

  function isCategoryMonthlyCustomerTable(table) {
    const headerText = cleanText([...table.querySelectorAll("thead th")].map(th => th.textContent).join(" ")).toUpperCase();
    return headerText.includes("SE") && headerText.includes("CUSTOMER") && headerText.includes("EXPIRY") && headerText.includes("DELIVERY TODATE") && headerText.includes("NOTES");
  }

  function extractCategoryMonthlyDelivery() {
    const summaries = [];
    const rows = [];
    const seen = new Set();

    getSourceDocument().querySelectorAll("table").forEach((table, tableIndex) => {
      if (isCategoryMonthlySummaryTable(table)) {
        [...table.querySelectorAll("tbody tr")].forEach((row, rowIndex) => {
          const cells = [...row.children].map(td => cleanText(td.textContent));
          if (cells.length < 8 || /^total$/i.test(cells[0])) return;
          summaries.push({
            tableIndex,
            rowIndex,
            seCode: cells[0] || "Not Assigned",
            seName: cleanText(row.children[0]?.getAttribute("title") || cells[0] || "Not Assigned"),
            orderBalance: firstNumber(cells[1]),
            platformBalance: firstNumber(cells[2]),
            lastYearDelivery: firstNumber(cells[3]),
            target: firstNumber(cells[4]),
            forwardBooking: firstNumber(cells[5]),
            deliveryToDate: firstNumber(cells[6]),
            difference: firstNumber(cells[7])
          });
        });
      }

      if (isCategoryMonthlyCustomerTable(table)) {
        [...table.querySelectorAll("tbody tr")].forEach((row, rowIndex) => {
          const cells = [...row.children].map(td => cleanText(td.textContent));
          if (cells.length < 10) return;
          const customerCell = row.children[1];
          const customerAnchor = customerCell?.querySelector("a strong") || customerCell?.querySelector("a") || customerCell;
          const companyName = cleanText(customerAnchor?.textContent || cells[1]);
          if (!companyName || /^total$/i.test(companyName)) return;
          const companyId = extractInlineCompanyId(row);
          const delivery = parseDeliveryBreakdown(cells[8] || "");
          const platformType = (cells[1].match(/Platform Type\s*\((.*?)\)/i) || [])[1] || "";
          const lastNoteDate = (cells[10] || "").match(/\d{2}\/\d{2}\/\d{4}/)?.[0] || "";
          const record = {
            tableIndex,
            rowIndex,
            companyId,
            seCode: cells[0] || "Not Assigned",
            seName: cleanText(row.children[0]?.getAttribute("title") || cells[0] || "Not Assigned"),
            companyName,
            platformType,
            expiryDate: (cells[2] || "").match(/\d{2}\/\d{2}\/\d{4}/)?.[0] || cells[2] || "",
            obBalance: firstNumber(cells[3]),
            pbBalance: firstNumber(cells[4]),
            lastYearDelivery: firstNumber(cells[5]),
            smsTargetDelivery: firstNumber(cells[6]),
            forwardBooking: firstNumber(cells[7]),
            smsDeliveryThisMonth: delivery.totalDelivery,
            localDelivery: delivery.localDelivery,
            platformDelivery: delivery.platformDelivery,
            difference: firstNumber(cells[9]),
            lastNoteDate,
            risks: [...new Set([...getRiskFlags(row), ...getCachedRisks(cacheKeyForInlineRow(row, companyName))])],
            balanceExpired: balanceExpiredFromCell(row.children[3]) || balanceExpiredFromCell(row.children[4]),
            approvedLinks: extractLinks(row)
          };
          const key = [record.companyId || record.companyName, record.seCode, record.expiryDate, record.smsTargetDelivery, record.smsDeliveryThisMonth].join("|");
          if (seen.has(key)) return;
          seen.add(key);
          rows.push(record);
        });
      }
    });

    return { summaries, rows, pageInfo: getPageInfo() };
  }
  async function crawlFirstLayer(companyRow) {
    const results = [];
    const links = (companyRow.approvedLinks || []).slice(0, 6);
    for (const link of links) {
      try {
        const response = await window.JORMALL_SMA_HOST_BRIDGE.fetchSmaText(link.href);
        const html = String(response.body || "");
        const doc = new DOMParser().parseFromString(html, "text/html");
        results.push({
          label: link.label || "Approved Link",
          href: link.href,
          status: Number(response.status || 0),
          title: doc.title || "",
          textSample: cleanText(doc.body ? doc.body.textContent : "").slice(0, 1600),
          tablesFound: doc.querySelectorAll("table").length
        });
      } catch (error) {
        results.push({ label: link.label || "Approved Link", href: link.href, error: error.message });
      }
    }
    return results;
  }




  function extractLeadRows() {
    const rows = [];
    const seen = new Set();
    getSourceDocument().querySelectorAll("table").forEach((table, tableIndex) => {
      const headers = [...table.querySelectorAll("thead th")].map(th => cleanText(th.textContent));
      const headerText = headers.join(" ").toLowerCase();
      const isLeadsTable = headerText.includes("assigned date") && headerText.includes("company name") && headerText.includes("open offers");
      if (!isLeadsTable) return;
      [...table.querySelectorAll("tbody tr")].forEach((row, rowIndex) => {
        const cells = [...row.children].map(td => cleanText(td.textContent));
        if (cells.length < 6) return;
        const firstAnchor = row.querySelector("td:nth-child(2) a[href*='makesearch']") || row.querySelector("td:nth-child(2) a[href*='cid=']") || row.querySelector("td:nth-child(2) a");
        const companyName = cleanText(firstAnchor ? firstAnchor.textContent : cells[1]);
        if (!companyName) return;
        const href = firstAnchor ? absoluteUrl(firstAnchor.getAttribute("href")) : "";
        const idMatch = href.match(/[?&]cid=(\d+)/i);
        const companyId = idMatch ? idMatch[1] : "";
        const assignedDate = cells[0] || "";
        const dateMatch = assignedDate.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
        const assignedDateSortable = dateMatch ? `${dateMatch[3]}-${dateMatch[2].padStart(2, "0")}-${dateMatch[1].padStart(2, "0")}` : assignedDate;
        const yearlyTarget = firstNumber(cells[5]);
        const lastNoteDate = (cells[6] || "").match(/\d{2}\/\d{2}\/\d{4}/)?.[0] || "";
        const record = {
          tableIndex,
          rowIndex,
          companyId,
          companyName,
          assignedDate,
          assignedDateSortable,
          smsDeliveryThisMonth: firstNumber(cells[2]),
          openOffers: firstNumber(cells[3]),
          forwardBooking: firstNumber(cells[4]),
          yearlyTarget,
          lastNoteDate,
          approvedLinks: extractLinks(row)
        };
        const key = [companyId || companyName, assignedDate, record.smsDeliveryThisMonth, record.openOffers, record.forwardBooking, yearlyTarget].join("|");
        if (seen.has(key)) return;
        seen.add(key);
        rows.push(record);
      });
    });
    return rows;
  }

  function extractCompanyNotes() {
    const pageInfo = getPageInfo();
    const url = pageInfo.url || getSourceUrl();
    const compid = (url.match(/[?&]compid=([^&]+)/i) || [])[1] || "";
    let companyName = "";
    const header = [...getSourceDocument().querySelectorAll(".table-header, h1, h2, h3, strong")]
      .map(x => cleanText(x.textContent)).find(t => /Company History Notes/i.test(t));
    if (header) {
      const m = header.match(/Company History Notes\s+for\s+["“]?\s*(.*?)\s*["”]?\s*$/i);
      companyName = m ? cleanText(m[1].replace(/^"|"$/g, "")) : "";
    }

    const notes = [];
    getSourceDocument().querySelectorAll("table").forEach((table, tableIndex) => {
      const headers = [...table.querySelectorAll("thead th")].map(th => cleanText(th.textContent).toLowerCase());
      const looksLikeNotes = headers.some(h => h.includes("date")) && headers.some(h => h.includes("added")) && headers.some(h => h.includes("notice"));
      if (!looksLikeNotes) return;
      [...table.querySelectorAll("tbody tr")].forEach((row, rowIndex) => {
        const cells = [...row.children].map(td => cleanText(td.textContent));
        if (cells.length < 3) return;
        const rawDate = cells[0] || "";
        const addedByCell = row.children[1];
        let department = "";
        let addedBy = cells[1] || "";
        const strongDept = addedByCell ? addedByCell.querySelector("strong") : null;
        if (strongDept) {
          department = cleanText(strongDept.textContent || "");
          addedBy = cleanText((addedByCell.textContent || "").replace(strongDept.textContent || "", ""));
        } else if (/\bDepartment\b|Dept\.|Customer Care|Accounting Department|Management Department/i.test(addedBy)) {
          const parts = (addedByCell?.textContent || addedBy).split(/\n+/).map(x => cleanText(x)).filter(Boolean);
          if (parts.length > 1) { addedBy = parts[0]; department = parts.slice(1).join(" "); }
        }
        const notice = cells[2] || "";
        if (!department) {
          const sentTo = notice.match(/sent to (?:Employee\s+)?([A-Za-z.()\s]+Department|Accounting Department|Customer Care Department|Order Processing Department|Technical Department|Mr\.\s*Jad Makdah)/i);
          department = sentTo ? cleanText(sentTo[1]) : "Miscellaneous";
        }
        if (!rawDate && !notice) return;
        const dateMatch = rawDate.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})\s*-\s*(\d{1,2}:\d{2})?/);
        let iso = "";
        if (dateMatch) {
          const dd = dateMatch[1].padStart(2, "0");
          const mm = dateMatch[2].padStart(2, "0");
          const yyyy = dateMatch[3];
          const time = (dateMatch[4] || "00:00").padStart(5, "0");
          iso = `${yyyy}-${mm}-${dd}T${time}:00`;
        }
        notes.push({ tableIndex, rowIndex, rawDate, iso, addedBy, department, notice });
      });
    });

    return { compid: decodeURIComponent(compid), companyName, notes, pageInfo };
  }

  window.JorMallSMAParser = {
    __setSource: setSource,
    getSourceDocument,
    getPageInfo,
    getSummaryStats,
    extractCompanyRows,
    extractLeadRows,
    extractCategoryMonthlyDelivery,
    extractCompanyNotes,
    crawlFirstLayer,
    allowedLinks: ALLOWED_LINK_LABELS
  };
})()
