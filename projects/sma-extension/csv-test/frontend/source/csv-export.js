(function () {
  "use strict";

  const EXPORT_TERMS = /\b(csv|excel|spreadsheet|export|download|downloadable)\b|(?:ملف\s*)?(?:سي[\s-]*إس[\s-]*في|اكسل|إكسل)|(?:صد[ّ]?ر|تنزيل|تحميل)\s*(?:ملف|تقرير|القائمة)?/i;
  const LARGE_REPORT_TERMS = /\b(all|every)\s+(?:the\s+)?(?:customers?|companies|clients?)\b|\b(?:detailed?|full|complete)\s+(?:list|report|breakdown)\b|(?:جميع|كل)\s+(?:العملاء|الشركات)|(?:تقرير|قائمة)\s+(?:تفصيلي|كامل)/i;
  const REPORT_SUBJECT_TERMS = /\b(balance|target|consumption|delivery|sales|customer|company|client|report|list|breakdown)\b|رصيد|هدف|استهلاك|تسليم|مبيعات|عميل|شركة|تقرير|قائمة/i;

  const columns = [
    ["Customer ID", "companyId"],
    ["Customer Name", "companyName"],
    ["OB Balance", "obBalance"],
    ["PB Balance", "pbBalance"],
    ["Total SMS Balance", "totalBalance"],
    ["SMS Target", "smsTargetDelivery"],
    ["Consumption Until Today", "smsDeliveryThisMonth"],
    ["Remaining Target", "remainingTarget"],
    ["Achievement %", "achievementPercent"],
    ["Forward Booking", "forwardBooking"],
    ["This Month Sales", "thisMonthSales"],
    ["YTD Sales", "ytdSales"],
    ["Yearly Target", "yearlyTarget"],
    ["Expiry / Order Type", "expiryDate"],
    ["Last Note Date", "lastNoteDate"],
    ["Risk Flags", "riskFlags"]
  ];

  function number(value) {
    const parsed = Number(String(value ?? "0").replace(/,/g, ""));
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function isCsvRequest(question) {
    const text = String(question || "").trim();
    return EXPORT_TERMS.test(text) || (LARGE_REPORT_TERMS.test(text) && REPORT_SUBJECT_TERMS.test(text));
  }

  function reportKind(question) {
    const text = String(question || "").toLowerCase();
    if (/\bzero\s+(?:consumption|delivery)\b|(?:zero|no)\s+usage|صفر\s+(?:استهلاك|تسليم)|بدون\s+(?:استهلاك|تسليم)/i.test(text)) return "zero-consumption";
    if (/\b(?:below|under|behind)\s+(?:the\s+)?target\b|أقل\s+من\s+الهدف|تحت\s+الهدف/i.test(text)) return "below-target";
    if (/\b(?:expired|expiry|expiring)\b|منتهي|انتهاء/i.test(text)) return "expiry";
    if (/\b(?:risk|risks|flagged)\b|مخاطر/i.test(text)) return "risk";
    return "all-customers";
  }

  function prepareRows(rows, question) {
    const kind = reportKind(question);
    const prepared = (Array.isArray(rows) ? rows : []).map(row => {
      const ob = number(row.obBalance);
      const pb = number(row.pbBalance);
      const target = number(row.smsTargetDelivery);
      const consumption = number(row.smsDeliveryThisMonth);
      return {
        companyId: String(row.companyId || ""),
        companyName: String(row.companyName || row.company || ""),
        obBalance: ob,
        pbBalance: pb,
        totalBalance: ob + pb,
        smsTargetDelivery: target,
        smsDeliveryThisMonth: consumption,
        remainingTarget: target - consumption,
        achievementPercent: target > 0 ? Number(((consumption / target) * 100).toFixed(2)) : "",
        forwardBooking: number(row.forwardBooking),
        thisMonthSales: number(row.thisMonthSales ?? row.monthlySales),
        ytdSales: number(row.ytdSales),
        yearlyTarget: number(row.yearlyTarget),
        expiryDate: String(row.expiryDate || row.orderType || ""),
        lastNoteDate: String(row.lastNoteDate || ""),
        riskFlags: Array.isArray(row.risks) ? row.risks.join(" | ") : String(row.flags || ""),
        balanceExpired: Boolean(row.balanceExpired)
      };
    });
    if (kind === "zero-consumption") return prepared.filter(row => row.smsDeliveryThisMonth === 0);
    if (kind === "below-target") return prepared.filter(row => row.smsTargetDelivery > 0 && row.smsDeliveryThisMonth < row.smsTargetDelivery);
    if (kind === "expiry") return prepared.filter(row => row.balanceExpired || /expired|منتهي/i.test(row.expiryDate));
    if (kind === "risk") return prepared.filter(row => row.riskFlags);
    return prepared;
  }

  function safeCell(value) {
    if (typeof value === "number") return String(value);
    let text = String(value ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    if (/^[=+\-@]/.test(text)) text = `'${text}`;
    return `"${text.replace(/"/g, '""')}"`;
  }

  function createCsv(rows) {
    const lines = [columns.map(column => safeCell(column[0])).join(",")];
    rows.forEach(row => lines.push(columns.map(column => safeCell(row[column[1]])).join(",")));
    return `\uFEFF${lines.join("\r\n")}\r\n`;
  }

  function totals(rows) {
    return rows.reduce((result, row) => {
      result.obBalance += number(row.obBalance);
      result.pbBalance += number(row.pbBalance);
      result.totalBalance += number(row.totalBalance);
      result.target += number(row.smsTargetDelivery);
      result.consumption += number(row.smsDeliveryThisMonth);
      result.remainingTarget += number(row.remainingTarget);
      return result;
    }, { rows: rows.length, obBalance: 0, pbBalance: 0, totalBalance: 0, target: 0, consumption: 0, remainingTarget: 0 });
  }

  function filename(question, now) {
    const kind = reportKind(question).replace(/[^a-z0-9-]/g, "");
    const date = (now || new Date()).toISOString().slice(0, 10);
    return `sma-${kind}-report-${date}.csv`;
  }

  function download(csv, name) {
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = name;
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  window.JorMallSMACsvExport = Object.freeze({
    columns, isCsvRequest, reportKind, prepareRows, createCsv, totals, filename, download
  });
})();
