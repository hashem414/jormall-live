(function () {
  const PANEL_ID = "jormall-sma-assistant-root";
  const sourceUrl = () => String(window.JorMallSMAParser?.getPageInfo?.().url || window.__JMA_SOURCE?.url || "");
  const sourceDocument = () => window.JorMallSMAParser?.getSourceDocument?.() || document;
  const notifyFrameState = (state) => { try { window.JORMALL_SMA_HOST_BRIDGE?.setFrameState?.(state); } catch (_) {} };
  const STANDALONE_CONFIG = window.JORMALL_SMA_OVERLAY_CONFIG || {};
  const API_GATEWAY_BASE_URL = String(
    STANDALONE_CONFIG.apiBaseUrl ||
    document.currentScript?.dataset?.apiBaseUrl ||
    window.location.origin
  ).replace(/\/$/, "");
  const API_GATEWAY_URL = `${API_GATEWAY_BASE_URL}/health`;
  const API_CHAT_URL = `${API_GATEWAY_BASE_URL}/api/chat`;
  const API_NOTIFY_SALES_PRIORITY_URL = `${API_GATEWAY_BASE_URL}/sma/notify-sales-priority`;

  async function apiFetch(url, options) {
    const bridge = window.JORMALL_SMA_EXTENSION_BRIDGE;
    if (bridge && typeof bridge.fetch === "function") return bridge.fetch(url, options || {});
    return fetch(url, options);
  }

  function normalizeListQuestion(question) {
    return String(question || "").toLowerCase().replace(/[’]/g, "'").replace(/\s+/g, " ").trim();
  }

  function isClientListQuestion(question) {
    const text = normalizeListQuestion(question);
    const hasClient = /\b(clients?|customers?|companies|company|accounts?)\b|العملاء|الزبائن|الشركات/.test(text);
    const asksForList = /\b(list|show|give|find|which|who|what|name|tell me|all|export|download|provide)\b|قائمة|اعرض|أعطني|اعطني|من هم/.test(text);
    const asksForFilter = /\b(below|under|less than|lower than|above|over|more than|greater than|at least|at most|between|meet target|achieve target|at target|on target|zero|no|none|without|didn'?t|did not|haven'?t|have not|to call|slow sent|active|inactive|overdue|expiring|missing|best|worst|top|only)\b/.test(text);
    return hasClient && (asksForList || asksForFilter);
  }

  function listMetricFromQuestion(text) {
    if (/\b(ytd|year.to.date|annual|yearly)\b/.test(text) && /\b(sales|target|revenue)\b/.test(text)) {
      return /\b(target|goal)\b/.test(text) && !/\b(ytd|year.to.date|sales|revenue)\b/.test(text) ? "yearlyTarget" : "ytdSales";
    }
    if (/\b(ob balance|order balance|order bal|ob)\b/.test(text)) return "obBalance";
    if (/\b(pb balance|platform balance|platform bal|pb)\b/.test(text)) return "pbBalance";
    if (/\b(total|combined) balance\b/.test(text)) return "totalBalance";
    if (/\b(difference|gap|shortfall|deficit|variance)\b/.test(text)) return "difference";
    if (/\b(forward booking|forward bookings|booking)\b/.test(text)) return "forwardBooking";
    if (/\b(this month|monthly) sales\b/.test(text)) return "thisMonthSales";
    if (/\b(yearly|annual) (sales )?target\b/.test(text)) return "yearlyTarget";
    if (/\b(ytd|year.to.date) sales\b/.test(text)) return "ytdSales";
    if (/\b(target|quota|goal)\b/.test(text) && /\b(message|sms|deliver|sent)\w*/.test(text)) {
      const comparesDeliveryToTarget = /\b(below|under|less than|lower than|fewer than|short of|behind|above|over|more than|greater than|higher than|exceed\w*|meet|achieve|compared to|vs|at|on)\s+(?:than\s+)?(?:the\s+)?(?:target|quota|goal)\b/.test(text) || /\b(didn'?t|did not|haven'?t|have not)\s+(?:meet|achieve)\b/.test(text);
      return comparesDeliveryToTarget ? "smsDeliveryThisMonth" : "smsTargetDelivery";
    }
    if (/\b(message|sms|deliver|sent)\w*/.test(text)) return "smsDeliveryThisMonth";
    if (/\b(sales|revenue)\b/.test(text)) return "thisMonthSales";
    if (/\b(balance|balances)\b/.test(text)) return "totalBalance";
    return "";
  }

  function listMetricValue(company, metric) {
    if (metric === "totalBalance") {
      const ob = listMetricValue(company, "obBalance"), pb = listMetricValue(company, "pbBalance");
      return ob === null && pb === null ? null : (ob || 0) + (pb || 0);
    }
    if (metric === "difference") {
      const reported = reportNumber(company.difference ?? company.differenceNumber);
      if (reported !== null) return reported;
      const delivery = listMetricValue(company, "smsDeliveryThisMonth"), target = listMetricValue(company, "smsTargetDelivery");
      return delivery === null || target === null ? null : delivery - target;
    }
    if (metric === "deliveryShortfall") {
      const delivery = listMetricValue(company, "smsDeliveryThisMonth"), target = listMetricValue(company, "smsTargetDelivery");
      return delivery === null || target === null ? null : Math.max(0, target - delivery);
    }
    const aliases = {
      smsDeliveryThisMonth: ["smsDeliveryThisMonth", "deliveryToDate", "smsDeliveryThisMonthNumber", "deliveryToDateNumber"],
      smsTargetDelivery: ["smsTargetDelivery", "target", "smsTargetDeliveryNumber", "targetNumber"],
      obBalance: ["obBalance", "orderBalance", "obBalanceNumber", "orderBalanceNumber"],
      pbBalance: ["pbBalance", "platformBalance", "pbBalanceNumber", "platformBalanceNumber"],
      forwardBooking: ["forwardBooking", "forwardBookingNumber"],
      thisMonthSales: ["thisMonthSales", "monthlySales", "monthlySalesNumber"],
      ytdSales: ["ytdSales", "ytdSalesNumber"],
      yearlyTarget: ["yearlyTarget", "annualTargetNumber"],
      localDelivery: ["localDelivery", "localDeliveryNumber"],
      platformDelivery: ["platformDelivery", "platformDeliveryNumber"],
      difference: ["difference", "differenceNumber"],
      lastYearDelivery: ["lastYearDelivery", "lastYearDeliveryNumber"]
    };
    for (const key of aliases[metric] || [metric]) {
      if (company[key] !== undefined && company[key] !== null) return reportNumber(company[key]);
    }
    return null;
  }

  function listName(company) {
    return String(company.companyName || company.company || company.customerName || company.customer || "");
  }

  function listMetricLabel(metric) {
    return ({
      smsDeliveryThisMonth: "SMS delivery this month",
      smsTargetDelivery: "SMS target this month",
      obBalance: "OB balance",
      pbBalance: "PB balance",
      totalBalance: "total SMS balance",
      forwardBooking: "forward booking",
      thisMonthSales: "sales this month",
      ytdSales: "year-to-date sales",
      yearlyTarget: "yearly sales target",
      localDelivery: "local delivery",
      platformDelivery: "platform delivery",
      difference: "delivery difference",
      deliveryShortfall: "delivery shortfall",
      lastYearDelivery: "last year delivery",
      companyName: "client name"
    })[metric] || metric;
  }

  const CLIENT_LIST_FIELDS = new Set([
    "companyName", "smsDeliveryThisMonth", "smsTargetDelivery", "obBalance", "pbBalance",
    "totalBalance", "forwardBooking", "thisMonthSales", "ytdSales", "yearlyTarget",
    "localDelivery", "platformDelivery", "difference", "deliveryShortfall", "lastYearDelivery",
    "lastNoteDate", "riskFlag"
  ]);
  const CLIENT_LIST_NUMERIC_FIELDS = new Set([
    "smsDeliveryThisMonth", "smsTargetDelivery", "obBalance", "pbBalance", "totalBalance",
    "forwardBooking", "thisMonthSales", "ytdSales", "yearlyTarget", "localDelivery",
    "platformDelivery", "difference", "deliveryShortfall", "lastYearDelivery"
  ]);

  function clientListFieldValue(company, field) {
    if (field === "companyName") return listName(company);
    if (field === "lastNoteDate") return company.lastNoteDate == null ? "" : String(company.lastNoteDate).trim();
    if (field === "riskFlag") {
      const values = company.risks ?? company.flags ?? [];
      return Array.isArray(values) ? values.map(String) : String(values).split(/[;,]/).map(value => value.trim()).filter(Boolean);
    }
    return listMetricValue(company, field);
  }

  function clientListConditionMatches(company, condition) {
    const { field, operator } = condition;
    const actual = clientListFieldValue(company, field);
    if (operator === "is_empty") return Array.isArray(actual) ? actual.length === 0 : actual === null || actual === undefined || String(actual).trim() === "";
    if (operator === "is_not_empty") return Array.isArray(actual) ? actual.length > 0 : actual !== null && actual !== undefined && String(actual).trim() !== "";
    if (actual === null || actual === undefined) return false;

    if (["contains", "starts_with", "equal"].includes(operator) && (field === "companyName" || field === "lastNoteDate" || field === "riskFlag")) {
      const expected = String(condition.value || "").trim().toLocaleLowerCase();
      const candidates = Array.isArray(actual) ? actual : [String(actual)];
      return candidates.some(candidate => {
        const value = String(candidate).toLocaleLowerCase();
        if (operator === "contains") return value.includes(expected);
        if (operator === "starts_with") return value.startsWith(expected);
        return value === expected;
      });
    }

    if (typeof actual === "number") {
      const left = actual;
      const right = condition.compareField
        ? listMetricValue(company, condition.compareField)
        : reportNumber(condition.value);
      if (right === null || right === undefined) return false;
      if (operator === "less_than") return left < right;
      if (operator === "less_or_equal") return left <= right;
      if (operator === "equal") return left === right;
      if (operator === "greater_than") return left > right;
      if (operator === "greater_or_equal") return left >= right;
      if (operator === "between") {
        const high = reportNumber(condition.secondValue);
        return high !== null && left >= right && left <= high;
      }
    }
    return false;
  }

  function applyClientListPlan(plan, companies) {
    const sourceRows = [...(Array.isArray(companies) ? companies : [])];
    const conditions = Array.isArray(plan?.conditions) ? plan.conditions : null;
    const numericOperators = new Set(["less_than", "less_or_equal", "equal", "greater_than", "greater_or_equal", "between"]);
    const textOperators = new Set(["equal", "contains", "starts_with", "is_empty", "is_not_empty"]);
    if (!plan?.understood || !conditions || conditions.length > 20 || conditions.some(condition => {
      if (!condition || !CLIENT_LIST_FIELDS.has(condition.field)) return true;
      if (condition.compareField && (!CLIENT_LIST_FIELDS.has(condition.compareField) || !CLIENT_LIST_NUMERIC_FIELDS.has(condition.compareField))) return true;
      if (CLIENT_LIST_NUMERIC_FIELDS.has(condition.field)) {
        if (!numericOperators.has(condition.operator)) return true;
        if (!condition.compareField && reportNumber(condition.value) === null) return true;
        return condition.operator === "between" && reportNumber(condition.secondValue) === null;
      }
      return !textOperators.has(condition.operator) || Boolean(condition.compareField);
    })) return { understood: false, rows: [], matchCount: 0 };

    const logic = plan.logic === "or" ? "or" : "and";
    let rows = conditions.length
      ? sourceRows.filter(company => logic === "or"
        ? conditions.some(condition => clientListConditionMatches(company, condition))
        : conditions.every(condition => clientListConditionMatches(company, condition)))
      : sourceRows;
    const matchCount = rows.length;
    const sort = Array.isArray(plan.sort) ? plan.sort.filter(item => item && CLIENT_LIST_FIELDS.has(item.field) && ["asc", "desc"].includes(item.direction)) : [];
    if (!sort.length) sort.push({ field: "companyName", direction: "asc" });
    rows.sort((left, right) => {
      for (const item of sort) {
        const a = clientListFieldValue(left, item.field), b = clientListFieldValue(right, item.field);
        if (a === null || a === undefined || a === "") return b === null || b === undefined || b === "" ? listName(left).localeCompare(listName(right)) : 1;
        if (b === null || b === undefined || b === "") return -1;
        const aValue = typeof a === "number" ? a : String(Array.isArray(a) ? a.join(", ") : a).toLocaleLowerCase();
        const bValue = typeof b === "number" ? b : String(Array.isArray(b) ? b.join(", ") : b).toLocaleLowerCase();
        if (aValue < bValue) return item.direction === "desc" ? 1 : -1;
        if (aValue > bValue) return item.direction === "desc" ? -1 : 1;
      }
      return listName(left).localeCompare(listName(right));
    });
    const rawLimit = Number(plan.limit);
    const limit = Number.isFinite(rawLimit) && rawLimit > 0 ? Math.min(Math.floor(rawLimit), 500) : 0;
    if (limit) rows = rows.slice(0, limit);
    const sortLabel = sort.map(item => `${listMetricLabel(item.field)} ${item.direction === "desc" ? "descending" : "ascending"}`).join(", ");
    return {
      understood: true,
      rows,
      matchCount,
      limit,
      filterLabel: String(plan.summary || "Requested client filter"),
      sortLabel: sortLabel || "sorted alphabetically by client name",
      metric: conditions[0]?.field || "",
      referenceMetric: conditions[0]?.compareField || ""
    };
  }

  function parseClientListPlan(answer) {
    const text = String(answer || "").trim();
    const start = text.indexOf("{");
    const end = text.lastIndexOf("}");
    if (start < 0 || end <= start) throw new Error("GPT did not return a client-list plan. Please retry or rephrase the request.");
    let plan;
    try { plan = JSON.parse(text.slice(start, end + 1)); }
    catch (_) { throw new Error("GPT returned an unreadable client-list plan. Please retry the request."); }
    if (!plan || typeof plan !== "object" || typeof plan.understood !== "boolean" || !Array.isArray(plan.conditions)) {
      throw new Error("GPT returned an incomplete client-list plan. Please retry the request.");
    }
    return plan;
  }

  async function requestClientListPlan(question) {
    const prompt = `Interpret this request as a filter and sort plan for a client list. Return exactly one JSON object and no markdown or explanation, with these keys: understood (boolean), summary (short label in the user's language), logic ("and" or "or"), conditions (array), sort (array), limit (integer), clarification (short question or empty string). Each condition must have field, operator, value, secondValue, compareField. Each sort item must have field and direction.

Allowed fields: companyName, smsDeliveryThisMonth (SMS delivered/sent this month), smsTargetDelivery (monthly SMS target), obBalance, pbBalance, totalBalance, forwardBooking, thisMonthSales, ytdSales, yearlyTarget, localDelivery, platformDelivery, difference (delivered minus target), deliveryShortfall (target minus delivered, floored at zero), lastYearDelivery, lastNoteDate, riskFlag (BT, ATT, Slow Sent, To Call).
Allowed operators: less_than, less_or_equal, equal, greater_than, greater_or_equal, between, contains, starts_with, is_empty, is_not_empty. For comparisons between two report fields, set compareField to the second field and value to an empty string. For numeric ranges put the lower bound in value and upper bound in secondValue. Use is_empty/is_not_empty for missing/present notes. Use multiple conditions and logic to preserve AND/OR. Add sorting only when requested; use deliveryShortfall descending for largest gap/shortfall. Set limit to 0 unless the user explicitly requests a row count. If the request is clear but phrased informally, infer its intent. For example, “clients that delivered less SMS than the target” means smsDeliveryThisMonth less_than smsTargetDelivery. If genuinely ambiguous or the requested field is unavailable, set understood=false and ask one concise clarification. Client records are not provided; do not request or invent them.

User request: ${JSON.stringify(String(question || ""))}`;
    const response = await apiFetch(API_CHAT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ screen: "client-list-intent", question: prompt })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `Gateway returned HTTP ${response.status}`);
    return { plan: parseClientListPlan(data.answer), model: data.model || "GPT" };
  }

  function matchClientList(question, companies) {
    const text = normalizeListQuestion(question);
    const rows = [...(Array.isArray(companies) ? companies : [])];
    const filterWords = /\b(below|under|less than|lower than|fewer than|short of|behind|above|over|more than|greater than|higher than|exceed\w*|at least|minimum|at most|maximum|between|equal|exactly|negative|positive|zero|none|without|no|didn'?t|did not|haven'?t|have not|starts? with|begin\w* with|to call|slow sent|bt|att)\b|لا|لم|بدون|صفر/.test(text);
    let metric = listMetricFromQuestion(text);
    let referenceMetric = "";
    if (/\b(target|quota|goal)\b/.test(text)) {
      if (metric === "ytdSales" || /\b(annual|yearly)\b/.test(text) && /\b(sales|revenue)\b/.test(text)) referenceMetric = "yearlyTarget";
      else if (metric === "smsDeliveryThisMonth" || !metric) { metric = "smsDeliveryThisMonth"; referenceMetric = "smsTargetDelivery"; }
    }
    if (!metric && /\b(message|sms|deliver|sent)\w*/.test(text)) metric = "smsDeliveryThisMonth";

    let operator = "";
    if (/\b(below|under|less than|lower than|fewer than|short of|behind|didn'?t meet|did not meet|haven'?t met|have not met)\b/.test(text)) operator = "lt";
    else if (/\b(above|over|more than|greater than|higher than|exceed\w*)\b/.test(text)) operator = "gt";
    else if (/\b(at least|minimum)\b/.test(text)) operator = "gte";
    else if (/\b(at most|maximum|no more than)\b/.test(text)) operator = "lte";
    else if (/\b(meet|achieve|reach|at target|on target)\b/.test(text)) operator = "gte";
    else if (/\b(negative|below zero)\b/.test(text)) operator = "lt";
    else if (/\b(positive|above zero)\b/.test(text)) operator = "gt";
    else if (/\b(equal|exactly|zero|none|without|no|didn'?t|did not|haven'?t|have not)\b|لا|لم|بدون|صفر/.test(text)) operator = "eq";

    const rangeMatch = text.match(/\bbetween\s+([\d,]+(?:\.\d+)?)\s+(?:and|to|-)\s+([\d,]+(?:\.\d+)?)/);
    const thresholdMatch = text.match(/\b(?:below(?:\s+than)?|under|less than|lower than|fewer than|above|over|more than|greater than|higher than|at least|at most|no more than|equal(?: to)?|exactly)\s+(?:jd\s*|sms\s*)?([\d,]+(?:\.\d+)?)/);
    let threshold = thresholdMatch ? reportNumber(thresholdMatch[1]) : null;
    if (threshold === null && /\b(negative|below zero|positive|above zero)\b/.test(text)) threshold = 0;
    if (operator === "eq" && /\b(zero|none|without|no|didn'?t|did not|haven'?t|have not)\b/.test(text)) threshold = 0;

    let filterLabel = "All client rows on the current report";
    if (rangeMatch && metric) {
      const low = reportNumber(rangeMatch[1]), high = reportNumber(rangeMatch[2]);
      rows.splice(0, rows.length, ...rows.filter(company => { const value = listMetricValue(company, metric); return value !== null && value >= low && value <= high; }));
      filterLabel = `${listMetricLabel(metric)} between ${low} and ${high}`;
    } else if (operator && metric && referenceMetric && threshold === null) {
      rows.splice(0, rows.length, ...rows.filter(company => {
        const value = listMetricValue(company, metric), target = listMetricValue(company, referenceMetric);
        return value !== null && target !== null && (operator === "lt" ? value < target : operator === "gt" ? value > target : operator === "eq" ? value === target : operator === "gte" ? value >= target : value <= target);
      }));
      filterLabel = `${listMetricLabel(metric)} ${operator === "lt" ? "below" : operator === "gt" ? "above" : operator === "eq" ? "equal to" : operator === "gte" ? "at least" : "at most"} ${listMetricLabel(referenceMetric)}`;
    } else if (operator && metric && threshold !== null) {
      rows.splice(0, rows.length, ...rows.filter(company => {
        const value = listMetricValue(company, metric);
        return value !== null && (operator === "lt" ? value < threshold : operator === "gt" ? value > threshold : operator === "eq" ? value === threshold : operator === "gte" ? value >= threshold : value <= threshold);
      }));
      filterLabel = `${listMetricLabel(metric)} ${operator === "lt" ? "below" : operator === "gt" ? "above" : operator === "eq" ? "equal to" : operator === "gte" ? "at least" : "at most"} ${threshold}`;
    } else if (operator === "eq" && metric && threshold === 0) {
      rows.splice(0, rows.length, ...rows.filter(company => listMetricValue(company, metric) === 0));
      filterLabel = `${metric} = 0`;
    } else if (metric === "smsDeliveryThisMonth" && /\b(sent|received|with messages|have messages)\b/.test(text) && !/\b(no|none|without|didn'?t|did not|haven'?t|have not)\b/.test(text)) {
      rows.splice(0, rows.length, ...rows.filter(company => { const value = listMetricValue(company, metric); return value !== null && value > 0; }));
      filterLabel = "Clients with SMS delivery above 0";
    } else if (/\b(no|without|missing)\s+(?:any\s+)?(?:last\s+)?notes?\b/.test(text)) {
      rows.splice(0, rows.length, ...rows.filter(company => !String(company.lastNoteDate || "").trim()));
      filterLabel = "Clients without a recorded note";
    } else if (/\b(with|having|has|have)\s+(?:a\s+)?(?:last\s+)?notes?\b/.test(text)) {
      rows.splice(0, rows.length, ...rows.filter(company => Boolean(String(company.lastNoteDate || "").trim())));
      filterLabel = "Clients with a recorded note";
    } else if (/\b(to call|slow sent|\bBT\b|\bATT\b)\b/i.test(text)) {
      const risk = /\bto call\b/i.test(text) ? "To Call" : /\bslow sent\b/i.test(text) ? "Slow Sent" : /\bATT\b/i.test(text) ? "ATT" : "BT";
      rows.splice(0, rows.length, ...rows.filter(company => (company.risks || []).includes(risk)));
      filterLabel = `Risk flag: ${risk}`;
    } else if (/\b(starts? with|begin\w* with)\s+([a-z0-9])/i.test(text)) {
      const initial = text.match(/\b(?:starts? with|begin\w* with)\s+([a-z0-9])/i)[1].toLowerCase();
      rows.splice(0, rows.length, ...rows.filter(company => listName(company).toLowerCase().startsWith(initial)));
      filterLabel = `Client name starts with ${initial.toUpperCase()}`;
    }
    const hasUnparsedCondition = /\b(who|whose|that|with|having|only|best|worst|top|high|low|active|inactive|overdue|expiring|missing|never)\b/.test(text) && !/\b(all|every)\b/.test(text);
    if ((filterWords || hasUnparsedCondition) && filterLabel === "All client rows on the current report") filterLabel = "Filter not understood; all client rows are shown";

    const explicitSort = text.match(/\b(?:sort|order|ordered) by\s+(name|client|customer|delivery|messages|sms|target|sales|balance|ob|pb|booking|difference|gap|shortfall|deficit)\b/);
    const alphabetical = /\b(alphabetical(?:ly)?|a to z|z to a)\b/.test(text);
    let sortMetric = metric;
    if (alphabetical) sortMetric = "companyName";
    else if (explicitSort) {
      const sortWord = explicitSort[1];
      sortMetric = /name|client|customer/.test(sortWord) ? "companyName" : /target/.test(sortWord) ? "smsTargetDelivery" : /sales/.test(sortWord) ? "thisMonthSales" : /ob/.test(sortWord) ? "obBalance" : /pb/.test(sortWord) ? "pbBalance" : /balance/.test(sortWord) ? "totalBalance" : /booking/.test(sortWord) ? "forwardBooking" : /gap|shortfall|deficit/.test(sortWord) ? "deliveryShortfall" : /difference/.test(sortWord) ? "difference" : "smsDeliveryThisMonth";
    }
    if (!explicitSort && !alphabetical && operator === "lt" && referenceMetric === "smsTargetDelivery" && /\b(shortfall|gap|deficit|largest|biggest|worst)\b/.test(text)) sortMetric = "deliveryShortfall";
    const descending = /\b(descending|desc|highest first|largest first|most first|worst first|biggest first|largest shortfall|biggest shortfall|largest gap|biggest gap|worst shortfall|z to a)\b/.test(text);
    if (sortMetric) {
      rows.sort((a, b) => {
        const av = sortMetric === "companyName" ? listName(a).toLowerCase() : listMetricValue(a, sortMetric);
        const bv = sortMetric === "companyName" ? listName(b).toLowerCase() : listMetricValue(b, sortMetric);
        if (av === null) return 1;
        if (bv === null) return -1;
        if (av < bv) return descending ? 1 : -1;
        if (av > bv) return descending ? -1 : 1;
        return listName(a).localeCompare(listName(b));
      });
    } else {
      rows.sort((a, b) => listName(a).localeCompare(listName(b)));
    }
    return { rows, filterLabel, metric, referenceMetric, hasFilter: filterWords, sortLabel: alphabetical ? (descending ? "sorted alphabetically Z to A" : "sorted alphabetically A to Z") : explicitSort ? `sorted by ${listMetricLabel(sortMetric)}${descending ? " descending" : " ascending"}` : `sorted by ${listMetricLabel(sortMetric || "companyName")}${descending ? " descending" : " ascending"}` };
  }

  function reportNumber(value) {
    if (value === null || value === undefined || String(value).trim() === "") return null;
    const match = String(value).replace(/,/g, "").match(/-?\d+(?:\.\d+)?/);
    if (!match) return null;
    const parsed = Number(match[0]);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function spreadsheetXmlText(value) {
    return String(value ?? "")
      .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function spreadsheetColumnName(number) {
    let result = "";
    let value = number;
    while (value > 0) {
      const remainder = (value - 1) % 26;
      result = String.fromCharCode(65 + remainder) + result;
      value = Math.floor((value - 1) / 26);
    }
    return result;
  }

  function spreadsheetWorksheet(headers, rows) {
    const allRows = [headers, ...rows];
    const lastColumn = spreadsheetColumnName(headers.length);
    const lastRow = Math.max(1, allRows.length);
    const columnWidths = headers.map((header, index) => {
      const width = index === 0 ? 30 : Math.max(16, Math.min(28, String(header).length + 3));
      return `<col min="${index + 1}" max="${index + 1}" width="${width}" customWidth="1"/>`;
    }).join("");
    const rowXml = allRows.map((row, rowIndex) => {
      const rowNumber = rowIndex + 1;
      const headerRow = rowIndex === 0;
      const cells = headers.map((_header, columnIndex) => {
        const reference = `${spreadsheetColumnName(columnIndex + 1)}${rowNumber}`;
        const value = row[columnIndex] ?? "";
        const style = headerRow ? " s=\"1\"" : "";
        if (typeof value === "number" && Number.isFinite(value)) {
          return `<c r="${reference}"${style} t="n"><v>${value}</v></c>`;
        }
        return `<c r="${reference}"${style} t="inlineStr"><is><t xml:space="preserve">${spreadsheetXmlText(value)}</t></is></c>`;
      }).join("");
      return `<row r="${rowNumber}"${headerRow ? " ht=\"22\" customHeight=\"1\"" : ""}>${cells}</row>`;
    }).join("");
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="15"/><cols>${columnWidths}</cols><sheetData>${rowXml}</sheetData><autoFilter ref="A1:${lastColumn}${lastRow}"/></worksheet>`;
  }

  function makeStoredZip(files) {
    const encoder = new TextEncoder();
    const crcTable = new Uint32Array(256);
    for (let n = 0; n < 256; n += 1) {
      let crc = n;
      for (let bit = 0; bit < 8; bit += 1) crc = (crc & 1) ? (0xEDB88320 ^ (crc >>> 1)) : (crc >>> 1);
      crcTable[n] = crc >>> 0;
    }
    const crc32 = bytes => {
      let crc = 0xFFFFFFFF;
      for (const byte of bytes) crc = crcTable[(crc ^ byte) & 0xFF] ^ (crc >>> 8);
      return (crc ^ 0xFFFFFFFF) >>> 0;
    };
    const write16 = (view, offset, value) => view.setUint16(offset, value, true);
    const write32 = (view, offset, value) => view.setUint32(offset, value >>> 0, true);
    const concatBytes = parts => {
      const output = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
      let offset = 0;
      for (const part of parts) { output.set(part, offset); offset += part.length; }
      return output;
    };

    const localParts = [];
    const centralParts = [];
    let localOffset = 0;
    for (const file of files) {
      const name = encoder.encode(file.name);
      const contents = encoder.encode(file.contents);
      const crc = crc32(contents);
      const local = new Uint8Array(30 + name.length + contents.length);
      const localView = new DataView(local.buffer);
      write32(localView, 0, 0x04034B50);
      write16(localView, 4, 20);
      write16(localView, 6, 0x0800);
      write16(localView, 8, 0);
      write16(localView, 10, 0);
      write16(localView, 12, 33);
      write32(localView, 14, crc);
      write32(localView, 18, contents.length);
      write32(localView, 22, contents.length);
      write16(localView, 26, name.length);
      write16(localView, 28, 0);
      local.set(name, 30);
      local.set(contents, 30 + name.length);
      localParts.push(local);

      const central = new Uint8Array(46 + name.length);
      const centralView = new DataView(central.buffer);
      write32(centralView, 0, 0x02014B50);
      write16(centralView, 4, 20);
      write16(centralView, 6, 20);
      write16(centralView, 8, 0x0800);
      write16(centralView, 10, 0);
      write16(centralView, 12, 0);
      write16(centralView, 14, 33);
      write32(centralView, 16, crc);
      write32(centralView, 20, contents.length);
      write32(centralView, 24, contents.length);
      write16(centralView, 28, name.length);
      write16(centralView, 30, 0);
      write16(centralView, 32, 0);
      write16(centralView, 34, 0);
      write16(centralView, 36, 0);
      write32(centralView, 38, 0);
      write32(centralView, 42, localOffset);
      central.set(name, 46);
      centralParts.push(central);
      localOffset += local.length;
    }

    const centralDirectory = concatBytes(centralParts);
    const end = new Uint8Array(22);
    const endView = new DataView(end.buffer);
    write32(endView, 0, 0x06054B50);
    write16(endView, 4, 0);
    write16(endView, 6, 0);
    write16(endView, 8, files.length);
    write16(endView, 10, files.length);
    write32(endView, 12, centralDirectory.length);
    write32(endView, 16, localOffset);
    write16(endView, 20, 0);
    return new Blob([...localParts, centralDirectory, end], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    });
  }

  function downloadClientListWorkbook(matchedCompanies, allCompanies) {
    const headers = [
      "Client", "Company ID", "Sales Executive / Category", "Platform / Order Type", "Expiry Date",
      "OB Balance (SMS)", "PB Balance (SMS)", "SMS Target This Month", "SMS Delivery This Month",
      "Local Delivery", "Platform Delivery", "Delivery Difference", "Forward Booking",
      "This-Month Sales (JD)", "YTD Sales (JD)", "Yearly Sales Target (JD)", "Last Year Delivery",
      "Last Note Date", "Risk Flags"
    ];
    const rowForCompany = company => [
      company.companyName || company.company || company.customerName || company.customer || "",
      company.companyId || "",
      [company.seCode, company.seName].filter(Boolean).join(" · "),
      company.platformType || company.orderType || "",
      company.expiryDate || "",
      listMetricValue(company, "obBalance"),
      listMetricValue(company, "pbBalance"),
      listMetricValue(company, "smsTargetDelivery"),
      listMetricValue(company, "smsDeliveryThisMonth"),
      listMetricValue(company, "localDelivery"),
      listMetricValue(company, "platformDelivery"),
      listMetricValue(company, "difference"),
      reportNumber(company.forwardBookingNumber ?? company.forwardBooking),
      reportNumber(company.thisMonthSales ?? company.monthlySales),
      reportNumber(company.ytdSales),
      reportNumber(company.yearlyTarget ?? company.annualTargetNumber),
      listMetricValue(company, "lastYearDelivery"),
      company.lastNoteDate || "",
      Array.isArray(company.risks) ? company.risks.join("; ") : String(company.risks || "")
    ];
    const allRows = allCompanies.map(rowForCompany);
    const matchedRows = matchedCompanies.map(rowForCompany);
    const styles = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Calibri"/><family val="2"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1F4E78"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`;
    const workbook = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Requested List" sheetId="1" r:id="rId1"/><sheet name="All Clients" sheetId="2" r:id="rId2"/></sheets></workbook>`;
    const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>`;
    const rootRelationships = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`;
    const workbookRelationships = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`;
    const blob = makeStoredZip([
      { name: "[Content_Types].xml", contents: contentTypes },
      { name: "_rels/.rels", contents: rootRelationships },
      { name: "xl/workbook.xml", contents: workbook },
      { name: "xl/_rels/workbook.xml.rels", contents: workbookRelationships },
      { name: "xl/styles.xml", contents: styles },
      { name: "xl/worksheets/sheet1.xml", contents: spreadsheetWorksheet(headers, matchedRows) },
      { name: "xl/worksheets/sheet2.xml", contents: spreadsheetWorksheet(headers, allRows) }
    ]);
    const date = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    const anchor = document.createElement("a");
    const objectUrl = URL.createObjectURL(blob);
    anchor.href = objectUrl;
    anchor.download = `sma-client-list-${date}.xlsx`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    return { allCount: allCompanies.length, matchedCount: matchedCompanies.length };
  }

  async function showClientListWorkbookPrompt(output, companies, question) {
    if (!isClientListQuestion(question)) return false;
    const allRows = Array.isArray(companies) ? companies : [];
    const period = getPageMonthYearLabel() || "current month";
    if (!allRows.length) {
      output.innerHTML = `<div class="jma-chat-answer"><strong>No client rows detected</strong><p>Open the SMA sales or monthly delivery report and refresh it before asking for the complete list.</p></div>`;
      return true;
    }
    output.innerHTML = `<div class="jma-chat-answer"><strong>Understanding your client-list request…</strong><p>GPT is interpreting the filter and sort; client records stay in this browser.</p></div>`;
    try {
      const { plan, model } = await requestClientListPlan(question);
      if (!plan.understood) {
        output.innerHTML = `<div class="jma-chat-answer"><strong>One detail needs clarification</strong><p>${escapeHtml(plan.clarification || "I could not determine the requested filter.")}</p></div>`;
        return true;
      }
      const result = applyClientListPlan(plan, allRows);
      if (!result.understood) {
        output.innerHTML = `<div class="jma-chat-answer"><strong>Could not safely apply that filter</strong><p>Please rephrase the report field or comparison. I did not treat all clients as matches.</p></div>`;
        return true;
      }
      const rows = result.rows;
      const firstCondition = Array.isArray(plan.conditions) ? plan.conditions[0] : null;
      const listHtml = rows.length
        ? `<details class="jma-client-list-results"><summary>Show ${rows.length} clients in the workbook</summary><ol>${rows.map(company => {
          const name = listName(company) || "Unnamed client";
          const value = result.metric ? listMetricValue(company, result.metric) : null;
          const reference = result.referenceMetric ? listMetricValue(company, result.referenceMetric) : null;
          const detail = value !== null ? ` <span class="jma-muted">(${fmt(value)}${reference !== null ? ` / comparison ${fmt(reference)}` : ""})</span>` : "";
          return `<li>${escapeHtml(name)}${detail}</li>`;
        }).join("")}</ol></details>`
        : `<p>No clients match this filter.</p>`;
      const limitText = result.limit && result.matchCount > rows.length ? `, showing the first ${rows.length} of ${result.matchCount} matches` : "";
      output.innerHTML = `<div class="jma-chat-answer"><strong>Excel client list ready · ${escapeHtml(model)}</strong><p>${rows.length} clients are in the Requested List${limitText}, matched from all ${allRows.length} rows on the current SMA page. Filter: <strong>${escapeHtml(result.filterLabel)}</strong>. Sort: ${escapeHtml(result.sortLabel)}. ${firstCondition ? "" : "No filter was specified, so the workbook includes all clients."}</p>${listHtml}<p>The workbook has <strong>Requested List</strong> and <strong>All Clients</strong> tabs. A download was started; use the button if your browser blocked it.</p><button class="jma-button" id="jma-download-client-list" type="button">Download Excel workbook</button></div>`;
      const download = () => downloadClientListWorkbook(rows, allRows);
      output.querySelector("#jma-download-client-list")?.addEventListener("click", download);
      download();
    } catch (error) {
      output.innerHTML = `<div class="jma-chat-answer jma-error-box"><strong>Could not prepare the client list</strong><p>${escapeHtml(error.message || "The gateway could not interpret the request.")}</p><p class="jma-muted">The list filter is interpreted by GPT. Check the test gateway connection and authentication, then retry.</p></div>`;
    }
    return true;
  }

  const rankingLimitState = {};
  const activeCompanyFilters = new Set();
  const DEFAULT_RANKING_LIMIT = 10;
  const RESULT_LIMIT_CHOICES = [10, 25, 50, 75, 100];
  const annualTableState = { key: "all", sortKey: "companyName", direction: "asc" };
  let executiveManagerialHidden = true;
  let salesExecutiveHidden = true;
  const salesExecutiveState = { statusFilter: "all", priorityFilter: "all", balanceMetric: "pb" };
  const TOP_PRIORITY_COMPANY_NAMES = ["GMD", "Nestle", "BioLab", "Fast Journey", "Balador", "Ahmad Al Samhouri", "JO Academy", "Al Rayhan", "Istiklal"];
  const TOP_PRIORITY_MIN_PB = {
    "gmd": 25000,
    "nestle": 50000,
    "biolab": 200000,
    "fast journey": 100000,
    "balador": 30000,
    "ahmad al samhouri": 100000,
    "jo academy": 500000,
    "al rayhan": 10000,
    "istiklal": 15000
  };
  const SALES_EXECUTIVE_REMOVED_TASKS_KEY = "jmaSalesExecutiveRemovedTasksV1";
  const SALES_PRIORITY_NOTIFIED_KEY = "jmaSalesPriorityNotifiedV1";
  const leadTableState = { sortKey: "assignedDateSortable", direction: "desc" };
  const categoryDeliveryState = {
    table: "customers",
    sortKey: "differenceNumber",
    direction: "asc",
    filter: "all",
    balanceFilter: "all",
    obBalanceFilter: "all",
    pbBalanceFilter: "all",
    platformTypeFilter: "all"
  };
  let riskSamplingTimer = null;
  const REPORT_SCREEN_CAPTURE_DELAY_MS = 2000;

  function el(tag, className) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    return node;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, s => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[s]));
  }


  function formatMarkdown(value) {
    const raw = String(value || "").replace(/\r\n/g, "\n");
    const lines = raw.split("\n");
    const out = [];
    let inUl = false;
    let inOl = false;

    const closeLists = () => {
      if (inUl) { out.push("</ul>"); inUl = false; }
      if (inOl) { out.push("</ol>"); inOl = false; }
    };

    const inline = (text) => escapeHtml(text)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/__(.+?)__/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        closeLists();
        continue;
      }

      const h = trimmed.match(/^(#{1,4})\s+(.+)$/);
      if (h) {
        closeLists();
        const level = Math.min(h[1].length + 2, 6);
        out.push(`<h${level}>${inline(h[2])}</h${level}>`);
        continue;
      }

      const bullet = trimmed.match(/^[-*•]\s+(.+)$/);
      if (bullet) {
        if (inOl) { out.push("</ol>"); inOl = false; }
        if (!inUl) { out.push("<ul>"); inUl = true; }
        out.push(`<li>${inline(bullet[1])}</li>`);
        continue;
      }

      const numbered = trimmed.match(/^\d+[.)]\s+(.+)$/);
      if (numbered) {
        if (inUl) { out.push("</ul>"); inUl = false; }
        if (!inOl) { out.push("<ol>"); inOl = true; }
        out.push(`<li>${inline(numbered[1])}</li>`);
        continue;
      }

      closeLists();
      out.push(`<p>${inline(trimmed)}</p>`);
    }

    closeLists();
    return out.join("\n");
  }

  function num(value) {
    return Number(String(value || "0").replace(/,/g, "")) || 0;
  }

  function fmt(value) {
    return num(value).toLocaleString();
  }

  function getCurrentMonthYearLabel() {
    const now = new Date();
    return `${now.toLocaleString("en", { month: "long" })} ${now.getFullYear()}`;
  }

  function getPageMonthYearLabel() {
    return getCurrentMonthYearLabel();
  }

  function companyActiveOrderUrl(company) {
    const id = company?.companyId || "";
    return id ? `http://sma/sma/activeorderreport.cfm?compid=${encodeURIComponent(id)}` : "#";
  }

  function totalBalanceOf(company) {
    return num(company.obBalanceNumber ?? company.obBalance) + num(company.pbBalanceNumber ?? company.pbBalance);
  }

  function riskCounts(companies) {
    const counts = { ATT: 0, BT: 0, "Slow Sent": 0, "To Call": 0 };
    companies.forEach(c => (c.risks || []).forEach(r => { if (counts[r] !== undefined) counts[r]++; }));
    return counts;
  }

  function rankCompanies(companies) {
    return [...companies].map(c => {
      const ob = num(c.obBalance), pb = num(c.pbBalance), target = num(c.smsTargetDelivery), delivered = num(c.smsDeliveryThisMonth);
      let score = ob + pb;
      score += (c.risks || []).length * 250000;
      if (target > 0 && delivered < target) score += (target - delivered) * 2;
      if (!c.lastNoteDate) score += 200000;
      return { ...c, score };
    }).sort((a, b) => b.score - a.score);
  }

  function renderRiskBadges(risks) {
    if (!risks || !risks.length) return `<span class="jma-risk ok">No risk flag</span>`;
    return risks.map(r => `<span class="jma-risk">${escapeHtml(r)}</span>`).join("\n");
  }

  function getCompaniesAndStats() {
    const companies = window.JorMallSMAParser.extractCompanyRows();
    const stats = window.JorMallSMAParser.getSummaryStats();
    const totals = companies.reduce((acc, c) => {
      acc.ob += num(c.obBalance);
      acc.pb += num(c.pbBalance);
      acc.delivery += num(c.smsDeliveryThisMonth);
      acc.target += num(c.smsTargetDelivery);
      return acc;
    }, { ob: 0, pb: 0, delivery: 0, target: 0 });
    return { companies, stats, totals, risks: riskCounts(companies), ranked: rankCompanies(companies) };
  }


  function getScopedCompanies(body) {
    const { companies, stats, totals, risks, ranked } = getCompaniesAndStats();
    const scope = body?.querySelector("#jma-analysis-scope")?.value || "all";
    const selectedIndex = Number(body?.querySelector("#jma-company-select")?.value || -1);
    const selected = companies.find(c => c.rowIndex === selectedIndex);
    const activeCompanies = scope === "selected" && selected ? [selected] : companies;
    const activeTotals = activeCompanies.reduce((acc, c) => {
      acc.ob += num(c.obBalance);
      acc.pb += num(c.pbBalance);
      acc.delivery += num(c.smsDeliveryThisMonth);
      acc.target += num(c.smsTargetDelivery);
      return acc;
    }, { ob: 0, pb: 0, delivery: 0, target: 0 });
    return {
      scope,
      selected,
      companies: activeCompanies,
      allCompanies: companies,
      stats,
      totals: activeTotals,
      risks: riskCounts(activeCompanies),
      ranked: rankCompanies(activeCompanies)
    };
  }

  function populateCompanySelector(body, companies) {
    const select = body.querySelector("#jma-company-select");
    if (!select) return;
    const oldValue = select.value;
    select.innerHTML = companies.map(c => `<option value="${c.rowIndex}">${escapeHtml(c.companyName || "Company")}</option>`).join("\n");
    if ([...select.options].some(o => o.value === oldValue)) select.value = oldValue;
  }

  function syncScopeUi(body) {
    const scope = body.querySelector("#jma-analysis-scope")?.value || "all";
    const companyWrap = body.querySelector("#jma-company-select-wrap");
    const badge = body.querySelector("#jma-mode-badge");
    if (companyWrap) companyWrap.style.display = scope === "selected" ? "block" : "none";
    if (badge) badge.textContent = scope === "selected" ? "Executive Mode: Selected Company" : "Executive Mode: Allocated / All Companies";
  }

  function syncManagerialScreenToggle(body) {
    const details = body.querySelector("#jma-executive-details");
    const toggle = body.querySelector("#jma-toggle-managerial-screen");
    if (details) details.classList.toggle("jma-hidden", executiveManagerialHidden);
    if (toggle) {
      toggle.innerHTML = executiveManagerialHidden
        ? '<span class="jma-toggle-arrow">▼</span><span>Managerial Screen — Expand</span>'
        : '<span class="jma-toggle-arrow">▲</span><span>Managerial Screen — Collapse</span>';
      toggle.setAttribute("aria-expanded", executiveManagerialHidden ? "false" : "true");
    }
  }

  function syncSalesExecutiveScreenToggle(body) {
    const details = body.querySelector("#jma-sales-executive-screen");
    const toggle = body.querySelector("#jma-toggle-sales-executive-screen");
    if (details) details.classList.toggle("jma-hidden", salesExecutiveHidden);
    if (toggle) {
      toggle.innerHTML = salesExecutiveHidden
        ? '<span class="jma-toggle-arrow">▼</span><span>Sales Executive Screen — Expand</span>'
        : '<span class="jma-toggle-arrow">▲</span><span>Sales Executive Screen — Collapse</span>';
      toggle.setAttribute("aria-expanded", salesExecutiveHidden ? "false" : "true");
    }
  }

  function localDateKey() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }

  function readJsonStorage(key, fallback) {
    try {
      const raw = window.localStorage ? localStorage.getItem(key) : "";
      return raw ? JSON.parse(raw) : fallback;
    } catch {
      return fallback;
    }
  }

  function writeJsonStorage(key, value) {
    try {
      if (window.localStorage) localStorage.setItem(key, JSON.stringify(value));
    } catch {}
  }

  function salesTaskKey(company, type) {
    return `${company?.companyId || company?.companyName || "company"}|${type}`;
  }

  function removedSalesTasks() {
    return new Set(readJsonStorage(SALES_EXECUTIVE_REMOVED_TASKS_KEY, []));
  }

  function saveRemovedSalesTask(key) {
    const removed = removedSalesTasks();
    removed.add(key);
    writeJsonStorage(SALES_EXECUTIVE_REMOVED_TASKS_KEY, [...removed]);
  }

  function companyStatusTypes(company) {
    const types = [];
    const risks = company?.risks || [];
    if (risks.includes("To Call")) types.push("toCall");
    if (isCompanyExpiredOrder(company)) types.push("expired");
    if (isCompanyExpiringSoon(company)) types.push("soon");
    if (risks.includes("ATT")) types.push("att");
    if (risks.includes("BT")) types.push("bt");
    if (risks.includes("Slow Sent")) types.push("slowSent");
    return types;
  }

  function salesTaskLabel(type) {
    if (type === "toCall") return "To Call";
    if (type === "expired") return "Expired";
    if (type === "soon") return "Soon to be Expired";
    if (type === "att") return "ATT";
    if (type === "bt") return "BT";
    if (type === "slowSent") return "Slow Sent";
    return type;
  }

  function normalizeCompanyName(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/&/g, " and ")
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  }

  function topPriorityKey(company) {
    const name = normalizeCompanyName(company?.companyName || "");
    if (!name) return "";
    return TOP_PRIORITY_COMPANY_NAMES.map(normalizeCompanyName).find(key => name === key || name.includes(key) || key.includes(name)) || "";
  }

  function isTopPriorityCompany(company) {
    return Boolean(topPriorityKey(company));
  }

  function minimumPbForCompany(company) {
    const key = topPriorityKey(company);
    return TOP_PRIORITY_MIN_PB[key] || 0;
  }

  function selectedSalesBalanceMetric() {
    const metric = salesExecutiveState.balanceMetric || "pb";
    if (metric === "ob") return { key: "ob", label: "OB Balance", currentLabel: "Current OB", minLabel: "Min OB" };
    if (metric === "total") return { key: "total", label: "Total Balance", currentLabel: "Current Total", minLabel: "Min Total" };
    return { key: "pb", label: "PB Balance", currentLabel: "Current PB", minLabel: "Min PB" };
  }

  function salesBalanceValue(company, metricKey) {
    const ob = num(company.obBalanceNumber ?? company.obBalance);
    const pb = num(company.pbBalanceNumber ?? company.pbBalance);
    if (metricKey === "ob") return ob;
    if (metricKey === "total") return ob + pb;
    return pb;
  }

  function pbEvaluationLabel(currentPb, minPb) {
    if (currentPb <= 0) return { label: "No PB Balance", cls: "danger" };
    if (minPb > 0 && currentPb < minPb) return { label: "Below Min PB", cls: "danger" };
    if (minPb > 0 && currentPb === minPb) return { label: "At Min PB", cls: "warn" };
    if (minPb > 0 && currentPb <= minPb * 1.2) return { label: "Near Min PB", cls: "warn" };
    return { label: "PB OK", cls: "good" };
  }

  function priorityClassForCompany(company, currentPb, minPb) {
    const types = companyStatusTypes(company);
    if (currentPb <= 0 || (minPb > 0 && currentPb < minPb) || isCompanyExpiredOrder(company) || types.includes("att")) {
      return { label: "Very Urgent", cls: "very-urgent", rank: 1 };
    }
    if ((minPb > 0 && currentPb <= minPb * 1.2) || types.includes("soon") || types.includes("toCall") || types.includes("bt") || types.includes("slowSent")) {
      return { label: "Urgent", cls: "urgent", rank: 2 };
    }
    return { label: "Medium", cls: "medium", rank: 3 };
  }

  function salesPriorityRows(companies) {
    const metric = selectedSalesBalanceMetric();
    return (companies || []).filter(isTopPriorityCompany).map(company => {
      const currentPb = num(company.pbBalanceNumber ?? company.pbBalance);
      const currentOb = num(company.obBalanceNumber ?? company.obBalance);
      const currentTotal = currentOb + currentPb;
      const minPb = minimumPbForCompany(company);
      const selectedBalance = salesBalanceValue(company, metric.key);
      const selectedMinBalance = minPb;
      const tasks = companyStatusTypes(company);
      const priority = priorityClassForCompany(company, currentPb, minPb);
      const pbEvaluation = pbEvaluationLabel(currentPb, minPb);
      return {
        ...company,
        currentPb,
        currentOb,
        currentTotal,
        minPb,
        selectedBalance,
        selectedMinBalance,
        selectedBalanceLabel: metric.label,
        selectedCurrentLabel: metric.currentLabel,
        selectedMinLabel: metric.minLabel,
        pbEvaluationLabel: pbEvaluation.label,
        pbEvaluationClass: pbEvaluation.cls,
        tasks,
        priorityLabel: priority.label,
        priorityClass: priority.cls,
        priorityRank: priority.rank
      };
    }).sort((a, b) => a.priorityRank - b.priorityRank || a.selectedBalance - b.selectedBalance || String(a.companyName || "").localeCompare(String(b.companyName || "")));
  }

  function salesExecutiveFilteredPriorityRows(rows) {
    return rows.filter(row => {
      const priorityOk = salesExecutiveState.priorityFilter === "all" || row.priorityClass === salesExecutiveState.priorityFilter;
      return priorityOk;
    });
  }

  function priorityTaskCounts(rows) {
    return {
      all: rows.length,
      toCall: rows.filter(row => row.tasks.includes("toCall")).length,
      expired: rows.filter(row => row.tasks.includes("expired")).length,
      soon: rows.filter(row => row.tasks.includes("soon")).length,
      att: rows.filter(row => row.tasks.includes("att")).length,
      bt: rows.filter(row => row.tasks.includes("bt")).length,
      slowSent: rows.filter(row => row.tasks.includes("slowSent")).length
    };
  }

  async function sendSalesPriorityNotifications(body, veryUrgentRows) {
    const box = body.querySelector("#jma-sales-exec-notification");
    if (!box || !veryUrgentRows.length) return;

    box.innerHTML = `<div class="jma-sales-alert"><strong>Very urgent priority detected</strong><span>${veryUrgentRows.length} company account(s) need immediate sales follow-up.</span></div>`;

    const dateKey = localDateKey();
    const notified = readJsonStorage(SALES_PRIORITY_NOTIFIED_KEY, {});
    const already = new Set(Array.isArray(notified[dateKey]) ? notified[dateKey] : []);
    const pendingRows = veryUrgentRows.filter(row => !already.has(row.companyId || row.companyName));
    if (!pendingRows.length) return;

    try {
      const response = await apiFetch(API_NOTIFY_SALES_PRIORITY_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          to: "sales@jormall.com",
          pageUrl: sourceUrl(),
          generatedAt: new Date().toISOString(),
          veryUrgentCompanies: pendingRows.slice(0, 25).map(row => ({
            companyName: row.companyName || "-",
            companyId: row.companyId || "",
            currentPb: row.currentPb,
            minPb: row.minPb,
            priority: row.priorityLabel,
            tasks: row.tasks.map(salesTaskLabel),
            expiryDate: row.expiryDate || ""
          }))
        })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
      pendingRows.forEach(row => already.add(row.companyId || row.companyName));
      notified[dateKey] = [...already];
      writeJsonStorage(SALES_PRIORITY_NOTIFIED_KEY, notified);
      box.innerHTML += `<div class="jma-sales-alert-note">Email notification sent to sales@jormall.com.</div>`;
    } catch (error) {
      box.innerHTML += `<div class="jma-sales-alert-note warn">Email notification could not be sent automatically. Check backend SMTP settings. ${escapeHtml(error.message || "")}</div>`;
    }
  }

  function renderSalesExecutiveDeliveryReport(body, companies) {
    const allDecorated = (companies || []).map(c => ({
      ...c,
      delivery: deliveryStatus(c),
      decision: expiryDecision(c),
      diff: num(c.smsDeliveryThisMonth) - num(c.smsTargetDelivery),
      totalBalanceNumber: totalBalanceOf(c)
    }));
    const decorated = applyCompanyFilters(allDecorated);
    const counts = decorated.reduce((acc, c) => {
      acc[c.delivery.label] = (acc[c.delivery.label] || 0) + 1;
      (c.risks || []).forEach(r => { acc[r] = (acc[r] || 0) + 1; });
      if ((c.risks || []).includes("BT") || (num(c.smsTargetDelivery) > 0 && num(c.smsDeliveryThisMonth) < num(c.smsTargetDelivery))) {
        acc.BT = Math.max(acc.BT || 0, 0) + ((c.risks || []).includes("BT") ? 0 : 1);
      }
      return acc;
    }, {});

    return `
      <div class="jma-section-title">Delivery Report Type Table</div>
      <p class="jma-muted">Status filters now apply to this moved Delivery Report table in the Sales Executive Screen.</p>
      ${filterBarHtml(allDecorated, decorated)}
      <div class="jma-report-grid five">
        ${reportKpi("Fast", counts["Fast"] || 0, "Companies", "good")}
        ${reportKpi("On Track", counts["On Track"] || 0, "Companies", "info")}
        ${reportKpi("Slow Sent", counts["Slow Sent"] || 0, "Companies", "warn")}
        ${reportKpi("BT", counts["BT"] || 0, "Companies", "danger")}
        ${reportKpi("ATT", counts["ATT"] || 0, "Companies", "danger")}
        ${reportKpi("To Call", counts["To Call"] || 0, "Companies", "purple")}
        ${reportKpi("Expired", decorated.filter(c => isCompanyExpiredOrder(c)).length, "Orders", "danger")}
        ${reportKpi("Soon <=2M", decorated.filter(c => isCompanyExpiringSoon(c)).length, "Orders", "warn")}
        ${reportKpi("Total", decorated.length, "Companies", "neutral")}
      </div>
      <div class="jma-definition-strip"><span title="No delivery 2 months."><strong>ATT</strong> No delivery 2 months.</span><span title="Delivery below target."><strong>BT</strong> Delivery below target.</span><span title="Average delivery longer than validity."><strong>Slow Sent</strong> Ave delivery longer than validity.</span><span title="29 Days not set a note."><strong>To Call</strong> 29 Days not set a note.</span></div>
      <div class="jma-table-wrap"><table class="jma-report-table" id="jma-sales-delivery-report-table"><thead><tr><th>#</th><th>Company</th><th>OB Balance</th><th>PB Balance</th><th>Total Balance</th><th>Total SMS Target Delivery — ${getPageMonthYearLabel()}</th><th>SMS Delivery — ${getPageMonthYearLabel()}</th><th>Delivery Difference</th><th>Delivery Status</th><th>Expiry / Balance Status</th><th>Last Note Date</th><th>Action Required</th></tr></thead><tbody>
        ${decorated.sort((a, b) => num(a.diff) - num(b.diff)).map((c, i) => `<tr><td>${i+1}</td><td>${companyCell(c)}</td><td class="${balanceClass(c)}">${fmt(c.obBalance)}</td><td class="${balanceClass(c)}">${fmt(c.pbBalance)}</td><td class="${balanceClass(c)}">${fmt(totalBalanceOf(c))}</td><td>${fmt(c.smsTargetDelivery)}</td><td>${fmt(c.smsDeliveryThisMonth)}</td><td class="${c.diff >= 0 ? 'jma-good-text' : 'jma-danger-text'}">${fmt(c.diff)}</td><td>${statusPill(c.delivery.label, c.delivery.cls)}</td><td>${isCompanyExpiredOrder(c) ? statusPill("Expired", "danger") : isCompanyExpiringSoon(c) ? statusPill("Soon <=2M", "warn") : statusPill(isBalanceExpired(c) ? "Expired Balance" : c.decision.status, isBalanceExpired(c) ? "danger" : c.decision.cls)}</td><td>${escapeHtml(c.lastNoteDate || '-')}</td><td>${escapeHtml(c.delivery.action)} ${isBalanceExpired(c) ? "Review expired OB/PB balance." : ""}</td></tr>`).join("\n") || `<tr><td colspan="12">No companies match the selected status filters.</td></tr>`}
      </tbody></table></div>
      <div class="jma-actionables"><h3>Delivery / Expiry Actionables</h3><div class="jma-action-grid">
        <div>${statusPill("Fast Delivery", "good")}<p>Prepare next order before balance finishes.</p></div>
        <div>${statusPill("On Track", "info")}<p>Continue monitoring.</p></div>
        <div>${statusPill("Slow Sent", "warn")}<p>Call client and schedule campaign.</p></div>
        <div>${statusPill("ATT", "danger")}<p>No delivery 2 months.</p></div><div>${statusPill("BT", "danger")}<p>Delivery below target.</p></div>
      </div></div>`;
  }

  function renderSalesExecutiveScreen(body, companies) {
    const host = body.querySelector("#jma-sales-executive-content");
    if (!host) return;
    const priorityRows = salesPriorityRows(companies);
    const filteredPriorityRows = salesExecutiveFilteredPriorityRows(priorityRows);
    const veryUrgentRows = priorityRows.filter(row => row.priorityClass === "very-urgent");
    const metric = selectedSalesBalanceMetric();
    const balanceButtons = [
      ["pb", "PB Balance"], ["ob", "OB Balance"], ["total", "Total Balance"]
    ].map(([key, label]) => `<button type="button" class="jma-filter-chip jma-balance-chip ${salesExecutiveState.balanceMetric === key ? "active" : ""}" data-sales-balance-filter="${key}">${escapeHtml(label)}</button>`).join("\n");
    const urgencyButtons = [
      ["all", "All Urgency"], ["very-urgent", "Red · Very Urgent"], ["urgent", "Yellow · Urgent"], ["medium", "Green · Medium"]
    ].map(([key, label]) => `<button type="button" class="jma-filter-chip jma-urgency-chip ${salesExecutiveState.priorityFilter === key ? "active" : ""}" data-sales-priority-filter="${key}">${label}</button>`).join("\n");

    host.innerHTML = `
      <div id="jma-sales-exec-notification"></div>
      <div class="jma-section-title">Top Priority Companies</div>
      <p class="jma-muted">Restricted to: ${TOP_PRIORITY_COMPANY_NAMES.map(escapeHtml).join(", ")}. PB must not go below the configured Min PB.</p>
      <div class="jma-priority-layout">
        <div class="jma-priority-filter-panel">
          <div class="jma-filter-head"><strong>Priority Filters</strong><span>Showing ${filteredPriorityRows.length} of ${priorityRows.length}</span></div>
          <div class="jma-filter-group-title">Balance Filter</div>
          <div class="jma-filter-row vertical">${balanceButtons}</div>
          <div class="jma-filter-group-title">Urgency</div>
          <div class="jma-filter-row vertical">${urgencyButtons}</div>
        </div>
        <div class="jma-priority-table-panel">
          <div class="jma-table-wrap"><table class="jma-report-table jma-priority-table"><thead><tr><th>#</th><th>Company Name</th><th>Min PB</th><th>${escapeHtml(metric.label)}</th><th>Priority</th></tr></thead><tbody>
            ${filteredPriorityRows.map((row, i) => `<tr class="jma-priority-row ${row.priorityClass}"><td>${i + 1}</td><td>${companyCell(row)}</td><td>${fmt(row.minPb)}</td><td><strong>${fmt(row.selectedBalance)}</strong></td><td>${statusPill(row.pbEvaluationLabel, row.pbEvaluationClass)}</td></tr>`).join("\n") || `<tr><td colspan="5">No configured top-priority companies match the selected filters on this page.</td></tr>`}
          </tbody></table></div>
        </div>
      </div>
      <div class="jma-sales-delivery-panel">
        ${renderSalesExecutiveDeliveryReport(body, companies)}
      </div>`;

    bindSalesExecutiveControls(body, companies);
    bindReportControls(body);
    sendSalesPriorityNotifications(body, veryUrgentRows);
  }

  function bindSalesExecutiveControls(body, companies) {
    body.querySelectorAll("[data-sales-priority-filter]").forEach(btn => {
      if (btn.dataset.jmaBoundSalesPriority === "1") return;
      btn.dataset.jmaBoundSalesPriority = "1";
      btn.addEventListener("click", () => {
        salesExecutiveState.priorityFilter = btn.getAttribute("data-sales-priority-filter") || "all";
        renderSalesExecutiveScreen(body, companies);
      });
    });
    body.querySelectorAll("[data-sales-balance-filter]").forEach(btn => {
      if (btn.dataset.jmaBoundSalesBalance === "1") return;
      btn.dataset.jmaBoundSalesBalance = "1";
      btn.addEventListener("click", () => {
        salesExecutiveState.balanceMetric = btn.getAttribute("data-sales-balance-filter") || "pb";
        renderSalesExecutiveScreen(body, companies);
      });
    });
  }

  function drawPageAnalysis(body) {
    const { companies, totals, risks, ranked, scope, selected } = getScopedCompanies(body);
    const underTarget = companies.filter(c => num(c.smsTargetDelivery) > 0 && num(c.smsDeliveryThisMonth) < num(c.smsTargetDelivery));
    const zeroDelivery = companies.filter(c => num(c.smsTargetDelivery) > 0 && num(c.smsDeliveryThisMonth) === 0);
    const highBalance = ranked.filter(c => num(c.obBalance) + num(c.pbBalance) > 0).slice(0, 5);
    const actions = [];
    if (zeroDelivery.length) actions.push(`Call ${zeroDelivery.length} companies with target but zero delivery this month.`);
    if (underTarget.length) actions.push(`Review ${underTarget.length} below-target companies and prioritize high-balance accounts.`);
    if (risks.ATT) actions.push(`Check ${risks.ATT} ATT accounts with no delivery for 2 months.`);
    if (risks["Slow Sent"]) actions.push(`Follow slow-sent accounts and push delivery before validity risk increases.`);
    if (risks["To Call"]) actions.push(`Update notes for ${risks["To Call"]} accounts marked To Call.`);
    if (!actions.length) actions.push("No urgent risk tasks detected from the current visible page.");

    body.querySelector("#jma-page-analysis").innerHTML = `
      <div class="jma-section-title">Summary of Delivery Issues</div>
      <ul class="jma-list">${actions.map(a => `<li>${escapeHtml(a)}</li>`).join("\n")}</ul>
      <div class="jma-definition-strip">
        <span title="No delivery 2 months."><strong>ATT</strong> No delivery 2 months.</span>
        <span title="Delivery below target."><strong>BT</strong> Delivery below target.</span>
        <span title="Average delivery longer than validity."><strong>Slow Sent</strong> Ave delivery longer than validity.</span>
        <span title="29 Days not set a note."><strong>To Call</strong> 29 Days not set a note.</span>
      </div>`;

    body.querySelectorAll(".jma-company-chip").forEach(btn => {
      btn.addEventListener("click", () => {
        const output = body.querySelector("#jma-report-output");
        if (output) output.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  function classifyAccount(company) {
    const totalBalance = totalBalanceOf(company);
    const ytd = num(company.ytdSalesNumber ?? company.ytdSales);
    const target = num(company.annualTargetNumber ?? company.yearlyTarget);
    const deliveryTarget = num(company.smsTargetDeliveryNumber ?? company.smsTargetDelivery);
    const delivery = num(company.smsDeliveryThisMonthNumber ?? company.smsDeliveryThisMonth);
    const risks = company.risks || [];
    if (risks.includes("ATT") || risks.includes("BT") || risks.includes("Slow Sent") || (deliveryTarget > 0 && delivery === 0)) return "Risk Accounts";
    if (totalBalance >= 1000000 || ytd >= 5000) return "VIP Accounts";
    if (target > 0 && ytd >= target) return "Strategic Accounts";
    if (totalBalance > 0 || delivery > 0 || ytd > 0) return "Growth Accounts";
    return "Dormant Accounts";
  }

  function topClassesSummary(rows) {
    const labels = ["VIP Accounts", "Strategic Accounts", "Growth Accounts", "Risk Accounts", "Dormant Accounts"];
    const grouped = Object.fromEntries(labels.map(label => [label, { label, count: 0, totalBalance: 0, ytdSales: 0, deliveryTarget: 0, delivery: 0 }]));
    rows.forEach(c => {
      const label = classifyAccount(c);
      const item = grouped[label];
      item.count += 1;
      item.totalBalance += totalBalanceOf(c);
      item.ytdSales += num(c.ytdSalesNumber ?? c.ytdSales);
      item.deliveryTarget += num(c.smsTargetDeliveryNumber ?? c.smsTargetDelivery);
      item.delivery += num(c.smsDeliveryThisMonthNumber ?? c.smsDeliveryThisMonth);
    });
    return labels.map(label => grouped[label]).sort((a,b) => b.count - a.count || b.totalBalance - a.totalBalance);
  }

  function classAction(label) {
    if (label === "VIP Accounts") return "Protect, renew, and upsell.";
    if (label === "Strategic Accounts") return "Maintain performance and plan next campaign.";
    if (label === "Growth Accounts") return "Convert balance and activity into more sales.";
    if (label === "Risk Accounts") return "Urgent follow-up for delivery or target risk.";
    return "Review for reactivation or cleanup.";
  }

  function buildTopClassCards(rows) {
    const summary = topClassesSummary(rows).filter(x => x.count > 0).slice(0, 5);
    return summary.map(x => `<button class="jma-company-chip jma-class-chip" type="button"><strong>${escapeHtml(x.label)}</strong><span>${x.count} companies · Total balance ${fmt(x.totalBalance)}</span></button>`).join("\n") || `<p class="jma-muted">No class data detected.</p>`;
  }

  function analyzeSelectedCompany(body) {
    const { companies } = getCompaniesAndStats();
    const select = body.querySelector("#jma-company-select");
    const rowIndex = Number(select?.value || 0);
    const company = companies.find(c => c.rowIndex === rowIndex) || companies[rowIndex] || companies[0];
    const output = body.querySelector("#jma-company-analysis");
    if (!company) {
      output.innerHTML = `<p class="jma-muted">No company table detected on this page.</p>`;
      return;
    }

    const ob = num(company.obBalance), pb = num(company.pbBalance), target = num(company.smsTargetDelivery), delivered = num(company.smsDeliveryThisMonth);
    const balance = ob + pb;
    const deliveryRate = target > 0 ? Math.round((delivered / target) * 100) : 0;
    const action = company.risks?.length
      ? `Priority follow-up because this account has ${company.risks.join(", ")} risk flag(s).`
      : balance > 0 && target > delivered
        ? "Good opportunity: balance exists and delivery is below target."
        : "Normal monitoring account.";

    output.innerHTML = `
      <div class="jma-company-head">
        <div><strong>${escapeHtml(company.companyName)}</strong><span>ID: ${escapeHtml(company.companyId || "N/A")}</span></div>
        <div class="jma-risks">${renderRiskBadges(company.risks)}</div>
      </div>
      <div class="jma-metrics">
        <div><span>OB Balance</span><strong>${fmt(ob)}</strong></div>
        <div><span>PB Balance</span><strong>${fmt(pb)}</strong></div>
        <div><span>Total Balance</span><strong>${fmt(balance)}</strong></div>
        <div><span>Total SMS Target Delivery — ${getPageMonthYearLabel()}</span><strong>${fmt(target)}</strong></div>
        <div><span>SMS Delivery — ${getPageMonthYearLabel()}</span><strong>${fmt(delivered)}</strong></div>
      </div>
      <div class="jma-progress"><span style="width:${Math.min(deliveryRate,100)}%"></span></div>
      <p class="jma-muted">Delivery progress: <strong>${deliveryRate}%</strong> of target.</p>
      <div class="jma-note"><strong>Recommended Action:</strong><br>${escapeHtml(action)}</div>
      <div class="jma-kv"><span>Order Type</span><strong>${escapeHtml(company.orderType || "-")}</strong></div>
      <div class="jma-kv"><span>YTD Sales</span><strong>${escapeHtml(company.ytdSales || "-")}</strong></div>
      <div class="jma-kv"><span>Yearly Target</span><strong>${escapeHtml(company.yearlyTarget || "-")}</strong></div>
      <div class="jma-kv"><span>Last Note</span><strong>${escapeHtml(company.lastNoteDate || "-")}</strong></div>`;
  }


  function safePct(part, whole) {
    const denominator = num(whole);
    if (!denominator) return "0.00%";
    return `${((num(part) / denominator) * 100).toFixed(2)}%`;
  }

  function moneyFmt(value) {
    return num(value).toLocaleString(undefined, { maximumFractionDigits: 3 });
  }

  function annualRows(companies) {
    return [...companies].map(c => {
      const ytdSales = num(c.ytdSales);
      const annualTarget = num(c.yearlyTarget);
      const monthlySales = num(c.thisMonthSales);
      const obBalance = num(c.obBalance);
      const pbBalance = num(c.pbBalance);
      const smsTargetDelivery = num(c.smsTargetDelivery);
      const smsDeliveryThisMonth = num(c.smsDeliveryThisMonth);
      const difference = ytdSales - annualTarget;
      return {
        ...c,
        obBalanceNumber: obBalance,
        pbBalanceNumber: pbBalance,
        totalBalanceNumber: obBalance + pbBalance,
        smsTargetDeliveryNumber: smsTargetDelivery,
        smsDeliveryThisMonthNumber: smsDeliveryThisMonth,
        monthlySalesNumber: monthlySales,
        ytdSalesNumber: ytdSales,
        annualTargetNumber: annualTarget,
        differenceNumber: difference,
        achievementNumber: annualTarget > 0 ? (ytdSales / annualTarget) * 100 : null
      };
    });
  }

  function sortDesc(rows, key) {
    return [...rows].sort((a, b) => num(b[key]) - num(a[key]));
  }

  function sortAsc(rows, key) {
    return [...rows].sort((a, b) => num(a[key]) - num(b[key]));
  }

  function achievementFmt(value) {
    return value === null || value === undefined || Number.isNaN(value) ? "No target" : `${value.toFixed(2)}%`;
  }

  function getRankingLimit(key) {
    return Math.max(1, Number(rankingLimitState[key] || DEFAULT_RANKING_LIMIT) || DEFAULT_RANKING_LIMIT);
  }

  function reportMiniTable(title, rows, columns, key = title) {
    const limit = getRankingLimit(key);
    const shownRows = rows.slice(0, limit);
    return `
      <div class="jma-section-title">${escapeHtml(title.replace(/Top 10/g, "Top"))}</div>
      <div class="jma-limit-controls" data-limit-key="${escapeHtml(key)}">
        <span>Show:</span>
        ${RESULT_LIMIT_CHOICES.map(choice => `<button type="button" class="jma-limit-btn ${limit === choice ? "active" : ""}" data-limit="${choice}">${choice}</button>`).join("\n")}
        <button type="button" class="jma-limit-btn ${limit >= 999999 ? "active" : ""}" data-limit="999999">Max</button>
        <input class="jma-limit-custom" type="number" min="1" placeholder="Custom" value="${RESULT_LIMIT_CHOICES.includes(limit) || limit >= 999999 ? "" : limit}">
        <button type="button" class="jma-limit-apply">Apply</button>
      </div>
      <div class="jma-table-wrap"><table class="jma-report-table jma-report-subtable"><thead><tr>
        <th>#</th>${columns.map(col => `<th>${escapeHtml(col.label)}</th>`).join("\n")}
      </tr></thead><tbody>
        ${shownRows.map((row, i) => `<tr><td>${i + 1}</td>${columns.map(col => `<td class="${col.className ? col.className(row) : ""}">${col.render(row)}</td>`).join("\n")}</tr>`).join("\n") || `<tr><td colspan="${columns.length + 1}">No companies found.</td></tr>`}
      </tbody></table></div>`;
  }

  function companyCell(c) {
    const name = escapeHtml(c.companyName || "-");
    const url = companyActiveOrderUrl(c);
    return url === "#" ? name : `<a class="jma-company-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">${name}</a>`;
  }

  function companyExpiryText(company) {
    return String(company?.expiryDate || company?.orderType || "").trim();
  }

  function addMonthsClamped(date, months) {
    const d = new Date(date.getTime());
    const originalDay = d.getDate();
    d.setMonth(d.getMonth() + months);
    if (d.getDate() !== originalDay) d.setDate(0);
    d.setHours(0, 0, 0, 0);
    return d;
  }

  function isCompanyExpiredOrder(company) {
    // Executive Reports expiry filters are based ONLY on the Expiry Date column, not red balance styling.
    return isExpiredByDate(companyExpiryText(company));
  }

  function isCompanyExpiringSoon(company) {
    const expiryText = companyExpiryText(company);
    if (isFreeOrder1900(expiryText) || isCompanyExpiredOrder(company)) return false;
    const dt = parseSmaDate(expiryText);
    if (!dt) return false;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    dt.setHours(0, 0, 0, 0);
    const limit = addMonthsClamped(today, 2);
    return dt >= today && dt <= limit;
  }

  const TABLE_FILTERS = [
    { key: "ATT", label: "ATT", tip: "No delivery 2 months.", test: c => (c.risks || []).includes("ATT") },
    { key: "BT", label: "BT", tip: "Delivery below target.", test: c => (c.risks || []).includes("BT") },
    { key: "Slow Sent", label: "Slow Sent", tip: "Average delivery longer than validity.", test: c => (c.risks || []).includes("Slow Sent") },
    { key: "To Call", label: "To Call", tip: "29 Days not set a note.", test: c => (c.risks || []).includes("To Call") },
    { key: "Expired Orders", label: "Expired Orders", tip: "Expiry Date is before today. Balance color/ATT does not make an order expired.", test: isCompanyExpiredOrder },
    { key: "Soon Expiring", label: "Soon to Expire ≤2M", tip: "Expiry Date is today through the next 2 months.", test: isCompanyExpiringSoon },
    { key: "Zero Sales", label: "Zero Sales", tip: "YTD sales equals zero.", test: c => num(c.ytdSalesNumber ?? c.ytdSales) === 0 },
    { key: "YTD Above Sales Target", label: "YTD Above Sales Target", tip: "YTD sales are equal to or above yearly sales target.", test: c => num(c.annualTargetNumber ?? c.yearlyTarget) > 0 && num(c.ytdSalesNumber ?? c.ytdSales) >= num(c.annualTargetNumber ?? c.yearlyTarget) },
    { key: "YTD Below Sales Target", label: "YTD Below Sales Target", tip: "YTD sales are below yearly sales target.", test: c => num(c.annualTargetNumber ?? c.yearlyTarget) > 0 && num(c.ytdSalesNumber ?? c.ytdSales) < num(c.annualTargetNumber ?? c.yearlyTarget) },
    { key: "Has OB Balance", label: "Has OB Balance", tip: "Open balance is greater than zero.", test: c => num(c.obBalanceNumber ?? c.obBalance) > 0 },
    { key: "Has PB Balance", label: "Has PB Balance", tip: "Platform/prepaid balance is greater than zero.", test: c => num(c.pbBalanceNumber ?? c.pbBalance) > 0 },
    { key: "Has FB", label: "Has FB", tip: "Forward booking is greater than zero.", test: c => num(c.forwardBooking) > 0 }
  ];

  function applyCompanyFilters(rows) {
    if (!activeCompanyFilters.size) return rows;
    return rows.filter(row => [...activeCompanyFilters].every(key => TABLE_FILTERS.find(f => f.key === key)?.test(row)));
  }

  function filterBarHtml(totalRows, visibleRows) {
    return `<div class="jma-table-filter-wrap">
      <div class="jma-filter-head"><strong>Table Filters</strong><span>Showing ${visibleRows.length} of ${totalRows.length} companies</span></div>
      <div class="jma-filter-row">
        <button type="button" class="jma-filter-chip ${activeCompanyFilters.size ? "" : "active"}" data-filter="__all">All - ${totalRows.length}</button>
        ${TABLE_FILTERS.map(f => {
          const count = totalRows.filter(row => f.test(row)).length;
          return `<button type="button" class="jma-filter-chip ${activeCompanyFilters.has(f.key) ? "active" : ""}" data-filter="${escapeHtml(f.key)}" title="${escapeHtml(f.tip || f.label)}">${escapeHtml(f.label)} - ${count}</button>`;
        }).join("\n")}
      </div>
    </div>`;
  }

  function rerenderCurrentScreen(body) {
    const screen = getCurrentSmaScreen();
    if (screen === "category-monthly-delivery") return drawCategoryMonthlyDeliveryBody();
    if (screen === "sales-report") {
      drawExecutiveReports(body);
      renderSalesExecutiveScreen(body, getCompaniesAndStats().companies);
      return;
    }
    if (screen === "company-notes") return drawCompanyNotesBody();
    return drawBody();
  }

  function makeAllReportTablesSortable(body) {
    body.querySelectorAll("table.jma-report-table").forEach((table, tableIndex) => {
      if (table.dataset.jmaSortableBound === "1") return;
      table.dataset.jmaSortableBound = "1";
      table.dataset.jmaSortColumn = table.dataset.jmaSortColumn || "";
      table.dataset.jmaSortDirection = table.dataset.jmaSortDirection || "asc";
      const headers = Array.from(table.querySelectorAll("thead th"));
      headers.forEach((th, colIndex) => {
        if (th.querySelector(".jma-sort-btn")) return;
        const label = th.innerHTML.trim() || "Column";
        th.innerHTML = `<button type="button" class="jma-sort-btn jma-dom-sort-btn" data-dom-sort-index="${colIndex}"><span class="jma-sort-label">${label}</span> <span class="jma-sort-arrow">↕</span></button>`;
      });
      table.querySelectorAll(".jma-dom-sort-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          const colIndex = Number(btn.getAttribute("data-dom-sort-index") || 0);
          const currentCol = table.dataset.jmaSortColumn;
          const nextDirection = currentCol === String(colIndex) && table.dataset.jmaSortDirection === "asc" ? "desc" : "asc";
          table.dataset.jmaSortColumn = String(colIndex);
          table.dataset.jmaSortDirection = nextDirection;
          const tbody = table.querySelector("tbody");
          if (!tbody) return;
          const rows = Array.from(tbody.querySelectorAll("tr")).filter(row => row.children.length > 1);
          const readCell = row => (row.children[colIndex]?.innerText || "").trim();
          const numericValue = value => {
            const cleaned = String(value).replace(/[^0-9.\-]/g, "");
            if (!cleaned || cleaned === "-" || cleaned === ".") return null;
            const parsed = Number(cleaned);
            return Number.isFinite(parsed) ? parsed : null;
          };
          rows.sort((a, b) => {
            const avText = readCell(a);
            const bvText = readCell(b);
            const avNum = numericValue(avText);
            const bvNum = numericValue(bvText);
            let result;
            if (avNum !== null && bvNum !== null) result = avNum - bvNum;
            else result = avText.localeCompare(bvText, undefined, { numeric: true, sensitivity: "base" });
            return nextDirection === "asc" ? result : -result;
          });
          rows.forEach(row => tbody.appendChild(row));
          table.querySelectorAll(".jma-dom-sort-btn .jma-sort-arrow").forEach(span => { span.textContent = "↕"; });
          const arrow = btn.querySelector(".jma-sort-arrow");
          if (arrow) arrow.textContent = nextDirection === "asc" ? "↑" : "↓";
        });
      });
    });
  }

  function bindReportControls(body) {
    makeAllReportTablesSortable(body);
    body.querySelectorAll("[data-filter]").forEach(btn => {
      if (btn.dataset.jmaBoundFilter === "1") return;
      btn.dataset.jmaBoundFilter = "1";
      btn.addEventListener("click", () => {
        const key = btn.getAttribute("data-filter");
        if (!key) return;
        if (key === "__all") activeCompanyFilters.clear();
        else if (activeCompanyFilters.has(key)) activeCompanyFilters.delete(key);
        else activeCompanyFilters.add(key);
        rerenderCurrentScreen(body);
      });
    });
    body.querySelectorAll(".jma-limit-controls").forEach(wrap => {
      const key = wrap.getAttribute("data-limit-key") || "default";
      if (key === "categoryCustomers" || key === "categorySummary") return;
      wrap.querySelectorAll(".jma-limit-btn").forEach(btn => btn.addEventListener("click", () => {
        rankingLimitState[key] = Number(btn.getAttribute("data-limit")) || DEFAULT_RANKING_LIMIT;
        rerenderCurrentScreen(body);
      }));
      const apply = () => {
        const input = wrap.querySelector(".jma-limit-custom");
        const val = Math.max(1, Number(input?.value || 0));
        if (val) {
          rankingLimitState[key] = val;
          rerenderCurrentScreen(body);
        }
      };
      wrap.querySelector(".jma-limit-apply")?.addEventListener("click", apply);
      wrap.querySelector(".jma-limit-custom")?.addEventListener("keydown", e => { if (e.key === "Enter") apply(); });
    });
  }

  function differenceClass(c) {
    return c.differenceNumber >= 0 ? "jma-good-text" : "jma-danger-text";
  }

  function deliveryStatus(company) {
    const target = num(company.smsTargetDelivery);
    const delivered = num(company.smsDeliveryThisMonth);
    const risks = company.risks || [];
    const combined = [];
    if (risks.includes("BT") || (target > 0 && delivered < target)) combined.push("BT");
    if (risks.includes("Slow Sent")) combined.push("Slow Sent");
    if (risks.includes("ATT")) combined.push("ATT");
    if (combined.length) {
      const label = combined.join("/");
      return {
        label,
        cls: combined.includes("ATT") || combined.includes("BT") ? "danger" : "warn",
        action: label.includes("ATT") ? "Urgent follow-up: no delivery for 2 months." : label.includes("BT") ? "Delivery is below target; prioritize campaign push." : "Call client and schedule delivery before validity risk increases."
      };
    }
    if (target > 0 && delivered > target) return { label: "Fast", cls: "good", action: "Prepare next order before balance ends." };
    return { label: "On Track", cls: "info", action: "Monitor" };
  }

  function expiryDecision(company) {
    const ob = num(company.obBalance);
    const pb = num(company.pbBalance);
    const ytd = num(company.ytdSales);
    const delivered = num(company.smsDeliveryThisMonth);
    const balance = ob + pb;
    if (delivered > 0 || ytd > 0) return { label: "Keep Active", cls: "info", status: "Active" };
    if (balance > 0) return { label: "Extend Account", cls: "good", status: "Balance Exists" };
    if (balance === 0 && ytd > 0) return { label: "Call Before Expiry", cls: "warn", status: "Sales History" };
    return { label: "Delete / Close", cls: "danger", status: "No Activity" };
  }

  function reportKpi(title, value, sub, cls = "info") {
    const unit = sub ? `<em class="jma-unit">${escapeHtml(sub)}</em>` : "";
    return `<div class="jma-report-kpi ${cls}"><span>${escapeHtml(title)}</span><strong>${escapeHtml(value)}</strong>${unit}</div>`;
  }

  function statCard(title, value, unit = "") {
    return `<div class="jma-stat"><span>${escapeHtml(title)}</span><strong>${escapeHtml(value)}</strong>${unit ? `<em class="jma-unit">${escapeHtml(unit)}</em>` : ""}</div>`;
  }

  function statusPill(label, cls) {
    return `<span class="jma-status ${cls}">${escapeHtml(label)}</span>`;
  }



  function isBalanceExpired(company) {
    return !!(company.balanceExpired || company.obExpired || company.pbExpired);
  }

  function balanceClass(company) {
    return isBalanceExpired(company) ? "jma-expired-balance" : "";
  }

  function balancesEndingSoonRows(rows) {
    return rows.filter(c => {
      const total = num(c.totalBalanceNumber);
      const delivery = num(c.smsDeliveryThisMonthNumber);
      const target = num(c.smsTargetDeliveryNumber);
      if (isBalanceExpired(c) || total <= 0) return false;
      if (target > 0 && total <= target) return true;
      if (delivery > 0 && total <= delivery * 1.5) return true;
      return total > 0 && total <= 5000;
    }).sort((a,b) => num(a.totalBalanceNumber) - num(b.totalBalanceNumber));
  }

  function priorityAchievementRows(rows) {
    const eligible = rows.filter(c => num(c.annualTargetNumber) > 0);
    const best = [...eligible].sort((a,b) => num(b.achievementNumber) - num(a.achievementNumber)).slice(0, 5).map(c => ({ ...c, prioritySide: "Best Achieving" }));
    const worst = [...eligible].sort((a,b) => num(a.achievementNumber) - num(b.achievementNumber)).slice(0, 5).map(c => ({ ...c, prioritySide: "Worst Achieving" }));
    return [...best, ...worst];
  }

  function priorityReasoning(rows) {
    const best = rows.filter(r => r.prioritySide === "Best Achieving");
    const worst = rows.filter(r => r.prioritySide === "Worst Achieving");
    const bestNames = best.slice(0, 3).map(r => r.companyName).join(", ") || "none";
    const worstNames = worst.slice(0, 3).map(r => r.companyName).join(", ") || "none";
    return `Best achieving accounts (${bestNames}) are prioritized for renewal, upsell, and reference campaigns because they already meet or exceed the sales target. Worst achieving accounts (${worstNames}) require management follow-up because their YTD sales are furthest behind target or achievement percentage is lowest.`;
  }

  function annualTableConfigs(rows, monthYearLabel) {
    const aboveTarget = rows.filter(c => c.annualTargetNumber > 0 && c.ytdSalesNumber >= c.annualTargetNumber);
    const belowTarget = rows.filter(c => c.annualTargetNumber > 0 && c.ytdSalesNumber < c.annualTargetNumber);
    const salesColumns = [
      { key: "companyName", label: "Company", type: "text", render: companyCell },
      { key: "totalBalanceNumber", label: "Total Balance (SMS)", type: "number", render: c => fmt(c.totalBalanceNumber), className: balanceClass },
      { key: "ytdSalesNumber", label: "YTD Sales (JD)", type: "number", render: c => moneyFmt(c.ytdSalesNumber) },
      { key: "annualTargetNumber", label: "Yearly Sales Target (JD)", type: "number", render: c => moneyFmt(c.annualTargetNumber) },
      { key: "differenceNumber", label: "Sales Difference (JD)", type: "number", render: c => moneyFmt(c.differenceNumber), className: differenceClass },
      { key: "achievementNumber", label: "Sales Achievement %", type: "number", render: c => achievementFmt(c.achievementNumber) }
    ];
    const balanceColumns = [
      { key: "companyName", label: "Company", type: "text", render: companyCell },
      { key: "obBalanceNumber", label: "OB Balance (SMS)", type: "number", render: c => fmt(c.obBalanceNumber), className: balanceClass },
      { key: "pbBalanceNumber", label: "PB Balance (SMS)", type: "number", render: c => fmt(c.pbBalanceNumber), className: balanceClass },
      { key: "totalBalanceNumber", label: "Total Balance (SMS)", type: "number", render: c => fmt(c.totalBalanceNumber), className: balanceClass },
      { key: "smsTargetDeliveryNumber", label: `SMS Target Delivery — ${monthYearLabel}`, type: "number", render: c => fmt(c.smsTargetDeliveryNumber) },
      { key: "smsDeliveryThisMonthNumber", label: `SMS Delivery — ${monthYearLabel}`, type: "number", render: c => fmt(c.smsDeliveryThisMonthNumber) },
      { key: "ytdSalesNumber", label: "YTD Sales (JD)", type: "number", render: c => moneyFmt(c.ytdSalesNumber) }
    ];
    return {
      all: { title: "ALL COMPANIES — NORMAL FILTER APPLICATION", rows: [...rows].sort((a,b) => String(a.companyName || "").localeCompare(String(b.companyName || ""))), columns: salesColumns, defaultSort: "companyName", defaultDirection: "asc", showAll: true, note: "Displays every company after the normal report filters are applied, without applying a ranking-specific condition." },
      topYtd: { title: "Top YTD Sales — Sales", rows: sortDesc(rows, "ytdSalesNumber"), columns: salesColumns, defaultSort: "ytdSalesNumber", defaultDirection: "desc", note: "Ranks companies by total sales from the start of the year." },
      topAchievement: { title: "Top Achievement % — Sales", rows: [...rows].filter(c => c.annualTargetNumber > 0).sort((a,b) => b.achievementNumber - a.achievementNumber), columns: salesColumns, defaultSort: "achievementNumber", defaultDirection: "desc", note: "Only companies with a yearly sales target are included." },
      topOb: { title: "Top OB Balance — Balance / Delivery", rows: sortDesc(rows, "obBalanceNumber"), columns: balanceColumns, defaultSort: "obBalanceNumber", defaultDirection: "desc", note: "Red OB/PB balance means the balance is treated as expired according to the SMA row styling." },
      topTotalBalance: { title: "Top Total Balance — Balance / Delivery", rows: sortDesc(rows, "totalBalanceNumber"), columns: balanceColumns, defaultSort: "totalBalanceNumber", defaultDirection: "desc", note: "Combines OB and PB balances." },
      topYearlyTarget: { title: "Top Yearly Sales Target — Sales", rows: sortDesc(rows, "annualTargetNumber"), columns: salesColumns, defaultSort: "annualTargetNumber", defaultDirection: "desc", note: "Ranks companies by yearly sales target value." },
      priorityAchievement: { title: "Priority: Best Achieving vs Worst Achieving — Sales", rows: priorityAchievementRows(rows), columns: [{ key: "prioritySide", label: "Priority Group", type: "text", render: c => escapeHtml(c.prioritySide || "-") }, ...salesColumns], defaultSort: "achievementNumber", defaultDirection: "desc", note: priorityReasoning(priorityAchievementRows(rows)) },
      endingBalances: { title: "Balances Ending Soon Not Expired — Balance / Delivery", rows: balancesEndingSoonRows(rows), columns: balanceColumns, defaultSort: "totalBalanceNumber", defaultDirection: "asc", note: "Estimated from current visible SMA data: positive balance, not red/expired, and low against current delivery or target." },
      bottomSales: { title: "Bottom Sales — Sales", rows: sortAsc(rows, "ytdSalesNumber"), columns: salesColumns, defaultSort: "ytdSalesNumber", defaultDirection: "asc", note: "Ranks companies by lowest YTD sales." }
    };
  }

  function annualDropdownHtml(configs) {
    const order = [
      "all",
      "topYtd",
      "topAchievement",
      "topOb",
      "topTotalBalance",
      "topYearlyTarget",
      "priorityAchievement",
      "endingBalances",
      "bottomSales"
    ];
    return `<div class="jma-unified-table-toolbar"><label>Report Table</label><select class="jma-input" id="jma-annual-table-select">${order.filter(key => configs[key]).map(key => `<option value="${key}" ${annualTableState.key === key ? "selected" : ""}>${escapeHtml(configs[key].title)}</option>`).join("\n")}</select></div>`;
  }

  function sortRowsForTable(rows, columns, config) {
    const sortKey = annualTableState.sortKey || config.defaultSort || columns[0]?.key;
    const direction = annualTableState.direction || config.defaultDirection || "desc";
    const col = columns.find(c => c.key === sortKey) || columns[0] || { type: "text" };
    return [...rows].sort((a,b) => {
      const av = col.type === "number" ? num(a[sortKey]) : String(a[sortKey] ?? "").toLowerCase();
      const bv = col.type === "number" ? num(b[sortKey]) : String(b[sortKey] ?? "").toLowerCase();
      const result = av > bv ? 1 : av < bv ? -1 : 0;
      return direction === "asc" ? result : -result;
    });
  }

  function unifiedAnnualTableHtml(config) {
    const sorted = sortRowsForTable(config.rows, config.columns, config);
    const limit = config.showAll ? sorted.length : getRankingLimit("annualUnified");
    const shownRows = sorted.slice(0, limit);
    const arrow = (key) => annualTableState.sortKey === key ? (annualTableState.direction === "asc" ? "↑" : "↓") : "↕";
    return `
      <div class="jma-section-title">${escapeHtml(config.title)}</div>
      <div class="jma-limit-controls" data-limit-key="annualUnified">
        <span>Results: ${Math.min(shownRows.length, sorted.length)} of ${sorted.length}</span>
        ${config.showAll ? `<span class="jma-muted">All filtered companies displayed</span>` : `${RESULT_LIMIT_CHOICES.map(choice => `<button type="button" class="jma-limit-btn ${limit === choice ? "active" : ""}" data-limit="${choice}">${choice}</button>`).join("\n")}<button type="button" class="jma-limit-btn ${limit >= 999999 ? "active" : ""}" data-limit="999999">Max</button><input class="jma-limit-custom" type="number" min="1" placeholder="Custom" value="${RESULT_LIMIT_CHOICES.includes(limit) || limit >= 999999 ? "" : limit}"><button type="button" class="jma-limit-apply">Apply</button>`}
      </div>
      <div class="jma-table-wrap"><table class="jma-report-table jma-report-subtable"><thead><tr>
        <th>#</th>${config.columns.map(col => `<th><button type="button" class="jma-sort-btn" data-sort-key="${escapeHtml(col.key)}">${escapeHtml(col.label)} <span>${arrow(col.key)}</span></button></th>`).join("\n")}
      </tr></thead><tbody>
        ${shownRows.map((row, i) => `<tr><td>${i + 1}</td>${config.columns.map(col => `<td class="${col.className ? col.className(row) : ""}">${col.render(row)}</td>`).join("\n")}</tr>`).join("\n") || `<tr><td colspan="${config.columns.length + 1}">No companies found.</td></tr>`}
      </tbody></table></div>
      <div class="jma-note jma-table-note"><strong>Reasoning note:</strong><br>${escapeHtml(config.note || "")}</div>`;
  }

  function leadCompanyCell(c) {
    const name = escapeHtml(c.companyName || "-");
    const id = c.companyId || "";
    const url = id ? `http://sma/sma/makesearch.cfm?cid=${encodeURIComponent(id)}` : "#";
    return url === "#" ? name : `<a class="jma-company-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">${name}</a>`;
  }

  function leadRowsForReport() {
    return (window.JorMallSMAParser.extractLeadRows ? window.JorMallSMAParser.extractLeadRows() : []).map(r => ({
      ...r,
      smsDeliveryThisMonthNumber: num(r.smsDeliveryThisMonth),
      openOffersNumber: num(r.openOffers),
      forwardBookingNumber: num(r.forwardBooking),
      yearlyTargetNumber: num(r.yearlyTarget)
    }));
  }

  function sortLeadRows(rows, columns) {
    const sortKey = leadTableState.sortKey || "assignedDateSortable";
    const direction = leadTableState.direction || "desc";
    const col = columns.find(c => c.key === sortKey) || columns[0] || { type: "text" };
    return [...rows].sort((a,b) => {
      const av = col.type === "number" ? num(a[sortKey]) : String(a[sortKey] ?? "").toLowerCase();
      const bv = col.type === "number" ? num(b[sortKey]) : String(b[sortKey] ?? "").toLowerCase();
      const result = av > bv ? 1 : av < bv ? -1 : 0;
      return direction === "asc" ? result : -result;
    });
  }

  function renderLeadsReport(body, host) {
    const rawRows = leadRowsForReport();
    const columns = [
      { key: "assignedDateSortable", label: "Assigned Date", type: "text", render: c => escapeHtml(c.assignedDate || "-") },
      { key: "companyName", label: "Lead Company", type: "text", render: leadCompanyCell },
      { key: "smsDeliveryThisMonthNumber", label: `SMS Delivery — ${getPageMonthYearLabel()}`, type: "number", render: c => fmt(c.smsDeliveryThisMonthNumber) },
      { key: "openOffersNumber", label: "Open Offers", type: "number", render: c => fmt(c.openOffersNumber) },
      { key: "forwardBookingNumber", label: "Forward Booking", type: "number", render: c => fmt(c.forwardBookingNumber) },
      { key: "yearlyTargetNumber", label: "Yearly Sales Target (JD)", type: "number", render: c => moneyFmt(c.yearlyTargetNumber) },
      { key: "lastNoteDate", label: "Last Note Date", type: "text", render: c => escapeHtml(c.lastNoteDate || "-") }
    ];
    const limit = getRankingLimit("leadsReport");
    const sorted = sortLeadRows(rawRows, columns);
    const shownRows = sorted.slice(0, limit);
    const arrow = (key) => leadTableState.sortKey === key ? (leadTableState.direction === "asc" ? "↑" : "↓") : "↕";
    const withOffers = rawRows.filter(r => num(r.openOffersNumber) > 0).length;
    const withDelivery = rawRows.filter(r => num(r.smsDeliveryThisMonthNumber) > 0).length;
    const totalFb = rawRows.reduce((sum, r) => sum + num(r.forwardBookingNumber), 0);

    host.innerHTML = `
      <div class="jma-report-scope">Leads Performance Report based on <strong>${rawRows.length}</strong> lead rows detected from the currently loaded SMA page.</div>
      <div class="jma-report-grid five">
        ${reportKpi("Total Leads", rawRows.length, "Leads", "info")}
        ${reportKpi("Leads with Open Offers", withOffers, "Leads", "warn")}
        ${reportKpi(`Leads with Delivery — ${getPageMonthYearLabel()}`, withDelivery, "Leads", "good")}
        ${reportKpi("Total Forward Booking", fmt(totalFb), "SMS", "purple")}
      </div>
      <div class="jma-section-title">Leads Performance — Sales / Delivery</div>
      <div class="jma-limit-controls" data-limit-key="leadsReport">
        <span>Results: ${Math.min(shownRows.length, sorted.length)} of ${sorted.length}</span>
        ${RESULT_LIMIT_CHOICES.map(choice => `<button type="button" class="jma-limit-btn ${limit === choice ? "active" : ""}" data-limit="${choice}">${choice}</button>`).join("\n")}
        <button type="button" class="jma-limit-btn ${limit >= 999999 ? "active" : ""}" data-limit="999999">Max</button>
        <input class="jma-limit-custom" type="number" min="1" placeholder="Custom" value="${RESULT_LIMIT_CHOICES.includes(limit) || limit >= 999999 ? "" : limit}">
        <button type="button" class="jma-limit-apply">Apply</button>
      </div>
      <div class="jma-table-wrap"><table class="jma-report-table jma-report-subtable"><thead><tr>
        <th>#</th>${columns.map(col => `<th><button type="button" class="jma-lead-sort-btn" data-sort-key="${escapeHtml(col.key)}">${escapeHtml(col.label)} <span>${arrow(col.key)}</span></button></th>`).join("\n")}
      </tr></thead><tbody>
        ${shownRows.map((row, i) => `<tr><td>${i + 1}</td>${columns.map(col => `<td>${col.render(row)}</td>`).join("\n")}</tr>`).join("\n") || `<tr><td colspan="${columns.length + 1}">No lead rows found on this SMA page.</td></tr>`}
      </tbody></table></div>
      <div class="jma-note jma-table-note"><strong>Reasoning note:</strong><br>This report separates leads from active/allocated company ranking. Use Open Offers to identify sales conversion work, and SMS Delivery / Forward Booking to identify lead movement into operational activity.</div>`;

    bindReportControls(body);
    body.querySelectorAll(".jma-lead-sort-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const key = btn.getAttribute("data-sort-key") || "assignedDateSortable";
        if (leadTableState.sortKey === key) leadTableState.direction = leadTableState.direction === "asc" ? "desc" : "asc";
        else {
          leadTableState.sortKey = key;
          leadTableState.direction = "desc";
        }
        drawExecutiveReports(body);
      });
    });
  }

  function drawExecutiveReports(body) {
    syncScopeUi(body);
    const scoped = getScopedCompanies(body);
    const { companies, totals, stats, scope, selected, allCompanies } = scoped;
    const reportType = body.querySelector("#jma-report-type")?.value || "annual";
    const host = body.querySelector("#jma-report-output");
    if (!host) return;

    if (!companies.length) {
      host.innerHTML = `<div class="jma-card"><p class="jma-muted">No SMA company rows were detected for this scope. Use Allocated Companies, select a company, or open the SMA sales assigned report and click Refresh Analysis.</p></div>`;
      return;
    }

    if (reportType === "annual") {
      const allRows = annualRows(companies);
      const rows = applyCompanyFilters(allRows);
      const ytdSales = rows.reduce((sum, c) => sum + c.ytdSalesNumber, 0);
      const yearlyTarget = rows.reduce((sum, c) => sum + c.annualTargetNumber, 0);
      const deliveredTarget = rows.reduce((sum, c) => sum + c.smsTargetDeliveryNumber, 0);
      const actualDelivery = rows.reduce((sum, c) => sum + c.smsDeliveryThisMonthNumber, 0);
      const monthlySales = rows.reduce((sum, c) => sum + c.monthlySalesNumber, 0);
      const difference = ytdSales - yearlyTarget;
      const aboveTarget = rows.filter(c => c.annualTargetNumber > 0 && c.ytdSalesNumber >= c.annualTargetNumber);
      const belowTarget = rows.filter(c => c.annualTargetNumber > 0 && c.ytdSalesNumber < c.annualTargetNumber);
      const zeroTarget = rows.filter(c => c.annualTargetNumber === 0);
      const expiredOrders = rows.filter(isCompanyExpiredOrder);
      const soonExpiringOrders = rows.filter(isCompanyExpiringSoon);
      const topYtd = sortDesc(rows, "ytdSalesNumber");
      const topYtdShare = ytdSales > 0 ? topYtd.slice(0, Math.min(10, topYtd.length)).reduce((sum, c) => sum + c.ytdSalesNumber, 0) / ytdSales : 0;
      const leadRows = window.JorMallSMAParser.extractLeadRows ? window.JorMallSMAParser.extractLeadRows() : [];
      const leadsWithOffers = leadRows.filter(l => num(l.openOffers) > 0).length;
      const leadsWithDelivery = leadRows.filter(l => num(l.smsDeliveryThisMonth) > 0).length;
      const monthYearLabel = getPageMonthYearLabel();
      const configs = annualTableConfigs(rows, monthYearLabel);
      if (!configs[annualTableState.key]) annualTableState.key = "all";
      const selectedConfig = configs[annualTableState.key];
      if (!annualTableState.sortKey || !(selectedConfig.columns || []).some(c => c.key === annualTableState.sortKey)) {
        annualTableState.sortKey = selectedConfig.defaultSort;
        annualTableState.direction = selectedConfig.defaultDirection || "desc";
      }

      host.innerHTML = `
        <div class="jma-report-scope">${scope === "selected" ? `Selected-company report for <strong>${escapeHtml(selected?.companyName || "selected company")}</strong>.` : `Executive allocated report based on <strong>${rows.length}</strong> filtered active companies from <strong>${companies.length}</strong> allocated active companies scraped from the currently loaded SMA tables.`} <br><span class="jma-muted">Total rows available on page: ${allCompanies.length}. Default mode is Allocated Companies.</span></div>
        ${filterBarHtml(allRows, rows)}
        <div class="jma-report-grid">
          ${reportKpi("Total OB Balance", fmt(rows.reduce((sum, c) => sum + c.obBalanceNumber, 0)), "SMS", "info")}
          ${reportKpi("Total PB Balance", fmt(rows.reduce((sum, c) => sum + c.pbBalanceNumber, 0)), "SMS", "good")}
          ${reportKpi("Total Balance", fmt(rows.reduce((sum, c) => sum + c.totalBalanceNumber, 0)), "SMS", "neutral")}
          ${reportKpi("Expired Orders", expiredOrders.length, "by date", "danger")}
          ${reportKpi("Soon to Expire", soonExpiringOrders.length, "≤ 2 months", "warn")}
          ${reportKpi(`Total SMS Target Delivery — ${monthYearLabel}`, fmt(deliveredTarget), "SMS", "purple")}
          ${reportKpi(`Total Actual SMS Delivery — ${monthYearLabel}`, fmt(actualDelivery), "SMS", "info")}
          ${reportKpi(`Total Monthly Sales — ${monthYearLabel}`, moneyFmt(monthlySales), "JD", "warn")}
          ${reportKpi("Total YTD Sales", moneyFmt(ytdSales), "JD", "good")}
          ${reportKpi("Total Yearly Sales Target", moneyFmt(yearlyTarget), "JD", "purple")}
          ${reportKpi("Overall Sales Difference", moneyFmt(difference), "JD", difference >= 0 ? "good" : "danger")}
          ${reportKpi("Overall Sales Achievement", safePct(ytdSales, yearlyTarget), "%", difference >= 0 ? "good" : "danger")}
          ${reportKpi("Detected Leads", leadRows.length, "leads", "info")}
          ${reportKpi("Leads with Open Offers", leadsWithOffers, "leads", "warn")}
          ${reportKpi(`Leads with Delivery — ${monthYearLabel}`, leadsWithDelivery, "leads", "good")}
        </div>

        <div class="jma-insights">
          <div><strong>${aboveTarget.length}</strong><span>YTD above sales target</span></div>
          <div><strong>${belowTarget.length}</strong><span>YTD below sales target</span></div>
          <div><strong>${zeroTarget.length}</strong><span>active companies with zero sales target</span></div>
          <div><strong>${expiredOrders.length}</strong><span>expired orders by date only</span></div>
          <div><strong>${soonExpiringOrders.length}</strong><span>orders expiring within 2 months</span></div>
          <div><strong>${(topYtdShare * 100).toFixed(1)}%</strong><span>YTD sales share of top 10</span></div>
        </div>

        ${annualDropdownHtml(configs)}
        ${unifiedAnnualTableHtml(selectedConfig)}

        <div class="jma-actionables"><h3>Management Insights</h3><div class="jma-action-grid">
          <div>${statusPill("YTD Above Sales Target", "good")}<p>${aboveTarget.length} companies are meeting or exceeding their yearly sales target. Prioritize renewal and upsell offers for the strongest accounts.</p></div>
          <div>${statusPill("YTD Below Sales Target", "warn")}<p>${belowTarget.length} companies need sales follow-up. Start with the largest negative gaps and high OB balance accounts.</p></div>
          <div>${statusPill("Zero Target", "purple")}<p>${zeroTarget.length} companies have no yearly sales target set. Add targets so management achievement percentages are reliable.</p></div>
          <div>${statusPill("Balance Expiry", "danger")}<p>Any OB/PB value styled in red by SMA is shown as expired in the report table.</p></div>
        </div></div>`;
      bindReportControls(body);
      body.querySelector("#jma-annual-table-select")?.addEventListener("change", e => {
        annualTableState.key = e.target.value;
        const next = annualTableConfigs(annualRows(getScopedCompanies(body).companies), getPageMonthYearLabel())[annualTableState.key];
        annualTableState.sortKey = next?.defaultSort || "companyName";
        annualTableState.direction = next?.defaultDirection || "desc";
        drawExecutiveReports(body);
      });
      body.querySelectorAll(".jma-sort-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          const key = btn.getAttribute("data-sort-key") || "companyName";
          if (annualTableState.sortKey === key) annualTableState.direction = annualTableState.direction === "asc" ? "desc" : "asc";
          else {
            annualTableState.sortKey = key;
            annualTableState.direction = "desc";
          }
          drawExecutiveReports(body);
        });
      });
      return;
    }

    if (reportType === "leads") {
      renderLeadsReport(body, host);
      return;
    }

    if (reportType === "statusFilters") {
      const allDecorated = companies.map(c => ({ ...c, delivery: deliveryStatus(c), decision: expiryDecision(c), diff: num(c.smsDeliveryThisMonth) - num(c.smsTargetDelivery), totalBalanceNumber: totalBalanceOf(c) }));
      const decorated = applyCompanyFilters(allDecorated);
      const counts = decorated.reduce((acc, c) => {
        acc[c.delivery.label] = (acc[c.delivery.label] || 0) + 1;
        (c.risks || []).forEach(r => { acc[r] = (acc[r] || 0) + 1; });
        return acc;
      }, {});
      host.innerHTML = `
        <div class="jma-report-scope">Status filter table applied to <strong>${companies.length}</strong> companies. Use the Table Filters below to narrow all rows by ATT, BT, Slow Sent, To Call, Expired, or Soon to Expire.</div>
        ${filterBarHtml(allDecorated, decorated)}
        <div class="jma-report-grid five">
          ${reportKpi("ATT", counts["ATT"] || 0, "Companies", "danger")}
          ${reportKpi("BT", counts["BT"] || 0, "Companies", "danger")}
          ${reportKpi("Slow Sent", counts["Slow Sent"] || 0, "Companies", "warn")}
          ${reportKpi("To Call", counts["To Call"] || 0, "Companies", "purple")}
          ${reportKpi("Expired", decorated.filter(c => isCompanyExpiredOrder(c)).length, "Orders", "danger")}
          ${reportKpi("Soon <=2M", decorated.filter(c => isCompanyExpiringSoon(c)).length, "Orders", "warn")}
          ${reportKpi("Total", decorated.length, "Companies", "neutral")}
        </div>
        <div class="jma-table-wrap"><table class="jma-report-table" id="jma-report-table"><thead><tr><th>#</th><th>Company</th><th>OB Balance</th><th>PB Balance</th><th>Total Balance</th><th>Delivery Status</th><th>Status Flags</th><th>Expiry</th><th>Action Required</th></tr></thead><tbody>
          ${decorated.map((c, i) => `<tr><td>${i+1}</td><td>${companyCell(c)}</td><td class="${balanceClass(c)}">${fmt(c.obBalance)}</td><td class="${balanceClass(c)}">${fmt(c.pbBalance)}</td><td class="${balanceClass(c)}">${fmt(totalBalanceOf(c))}</td><td>${statusPill(c.delivery.label, c.delivery.cls)}</td><td>${(c.risks || []).map(escapeHtml).join(", ") || "-"}</td><td>${isCompanyExpiredOrder(c) ? statusPill("Expired", "danger") : isCompanyExpiringSoon(c) ? statusPill("Soon <=2M", "warn") : "-"}</td><td>${escapeHtml(c.delivery.action || "Review")}</td></tr>`).join("\n") || `<tr><td colspan="9">No companies found.</td></tr>`}
        </tbody></table></div>`;
      bindReportControls(body);
      return;
    }

    if (reportType === "delivery") {
      const allDecorated = companies.map(c => ({ ...c, delivery: deliveryStatus(c), decision: expiryDecision(c), diff: num(c.smsDeliveryThisMonth) - num(c.smsTargetDelivery), totalBalanceNumber: totalBalanceOf(c) }));
      const decorated = applyCompanyFilters(allDecorated);
      const counts = decorated.reduce((acc, c) => {
        acc[c.delivery.label] = (acc[c.delivery.label] || 0) + 1;
        (c.risks || []).forEach(r => { acc[r] = (acc[r] || 0) + 1; });
        if ((c.risks || []).includes("BT") || (num(c.smsTargetDelivery) > 0 && num(c.smsDeliveryThisMonth) < num(c.smsTargetDelivery))) acc.BT = Math.max(acc.BT || 0, 0) + ((c.risks || []).includes("BT") ? 0 : 1);
        return acc;
      }, {});
      host.innerHTML = `
        <div class="jma-report-scope">${scope === "selected" ? `Delivery methodology for <strong>${escapeHtml(selected?.companyName || "selected company")}</strong>.` : `Delivery methodology applied to all <strong>${companies.length}</strong> companies in the currently loaded SMA table.`} <br><span class="jma-muted">Total rows available on page: ${allCompanies.length}. Default mode is Allocated Companies.</span></div>
        ${filterBarHtml(allDecorated, decorated)}
        <div class="jma-report-grid five">
          ${reportKpi("Fast", counts["Fast"] || 0, "Companies", "good")}
          ${reportKpi("On Track", counts["On Track"] || 0, "Companies", "info")}
          ${reportKpi("Slow Sent", counts["Slow Sent"] || 0, "Companies", "warn")}
          ${reportKpi("BT", counts["BT"] || 0, "Companies", "danger")}
          ${reportKpi("ATT", counts["ATT"] || 0, "Companies", "danger")}
          ${reportKpi("To Call", counts["To Call"] || 0, "Companies", "purple")}
          ${reportKpi("Expired Balance", decorated.filter(c => isBalanceExpired(c)).length, "Accounts", "danger")}
          ${reportKpi("Total", decorated.length, "Companies", "neutral")}
        </div>
        <div class="jma-definition-strip"><span title="No delivery 2 months."><strong>ATT</strong> No delivery 2 months.</span><span title="Delivery below target."><strong>BT</strong> Delivery below target.</span><span title="Average delivery longer than validity."><strong>Slow Sent</strong> Ave delivery longer than validity.</span><span title="29 Days not set a note."><strong>To Call</strong> 29 Days not set a note.</span></div>
        <div class="jma-table-wrap"><table class="jma-report-table" id="jma-report-table"><thead><tr><th>#</th><th>Company</th><th>OB Balance</th><th>PB Balance</th><th>Total Balance</th><th>Total SMS Target Delivery — ${getPageMonthYearLabel()}</th><th>SMS Delivery — ${getPageMonthYearLabel()}</th><th>Delivery Difference</th><th>Delivery Status</th><th>Expiry / Balance Status</th><th>Last Note Date</th><th>Action Required</th></tr></thead><tbody>
          ${decorated.sort((a, b) => num(a.diff) - num(b.diff)).map((c, i) => `<tr><td>${i+1}</td><td>${companyCell(c)}</td><td class="${balanceClass(c)}">${fmt(c.obBalance)}</td><td class="${balanceClass(c)}">${fmt(c.pbBalance)}</td><td class="${balanceClass(c)}">${fmt(totalBalanceOf(c))}</td><td>${fmt(c.smsTargetDelivery)}</td><td>${fmt(c.smsDeliveryThisMonth)}</td><td class="${c.diff >= 0 ? 'jma-good-text' : 'jma-danger-text'}">${fmt(c.diff)}</td><td>${statusPill(c.delivery.label, c.delivery.cls)}</td><td>${statusPill(isBalanceExpired(c) ? "Expired Balance" : c.decision.status, isBalanceExpired(c) ? "danger" : c.decision.cls)}</td><td>${escapeHtml(c.lastNoteDate || '-')}</td><td>${escapeHtml(c.delivery.action)} ${isBalanceExpired(c) ? "Review expired OB/PB balance." : ""}</td></tr>`).join("\n")}
        </tbody></table></div>
        <div class="jma-actionables"><h3>Delivery / Expiry Actionables</h3><div class="jma-action-grid">
          <div>${statusPill("Fast Delivery", "good")}<p>Prepare next order before balance finishes.</p></div>
          <div>${statusPill("On Track", "info")}<p>Continue monitoring.</p></div>
          <div>${statusPill("Slow Sent", "warn")}<p>Call client and schedule campaign.</p></div>
          <div>${statusPill("ATT", "danger")}<p>No delivery 2 months.</p></div><div>${statusPill("BT", "danger")}<p>Delivery below target.</p></div>
        </div></div>`;
      bindReportControls(body);
      return;
    }

    const allDecorated = companies.map(c => ({ ...c, decision: expiryDecision(c), totalBalanceNumber: totalBalanceOf(c) }));
    const decorated = applyCompanyFilters(allDecorated);
    const counts = decorated.reduce((acc, c) => { acc[c.decision.label] = (acc[c.decision.label] || 0) + 1; return acc; }, {});
    host.innerHTML = `
      <div class="jma-report-scope">${scope === "selected" ? `Expiry/account-decision methodology for <strong>${escapeHtml(selected?.companyName || "selected company")}</strong>.` : `Expiry/account-decision methodology applied to all <strong>${companies.length}</strong> companies in the currently loaded SMA table.`} <br><span class="jma-muted">Total rows available on page: ${allCompanies.length}. Default mode is Allocated Companies.</span></div>
      ${filterBarHtml(allDecorated, decorated)}
      <div class="jma-report-grid five">
        ${reportKpi("Extend Account", counts["Extend Account"] || 0, "Accounts", "good")}
        ${reportKpi("Call Before Expiry", counts["Call Before Expiry"] || 0, "Accounts", "warn")}
        ${reportKpi("Delete / Close", counts["Delete / Close"] || 0, "Accounts", "danger")}
        ${reportKpi("Keep Active", counts["Keep Active"] || 0, "Accounts", "info")}
        ${reportKpi("Total", decorated.length, "Accounts", "neutral")}
      </div>
      <div class="jma-table-wrap"><table class="jma-report-table" id="jma-report-table"><thead><tr><th>#</th><th>Company</th><th>OB Balance</th><th>PB Balance</th><th>Total Balance</th><th>Order Type</th><th>Last Delivery Date</th><th>Last Note Date</th><th>YTD Sales</th><th>Expiry Status</th><th>Suggested Decision</th></tr></thead><tbody>
        ${decorated.sort((a, b) => (num(b.obBalance) + num(b.pbBalance)) - (num(a.obBalance) + num(a.pbBalance))).map((c, i) => `<tr><td>${i+1}</td><td>${companyCell(c)}</td><td>${fmt(c.obBalance)}</td><td>${fmt(c.pbBalance)}</td><td>${fmt(totalBalanceOf(c))}</td><td>${escapeHtml(c.orderType || '-')}</td><td>-</td><td>${escapeHtml(c.lastNoteDate || '-')}</td><td>${moneyFmt(c.ytdSales)}</td><td>${statusPill(c.decision.status, c.decision.cls)}</td><td>${statusPill(c.decision.label, c.decision.cls)}</td></tr>`).join("\n")}
      </tbody></table></div>
      <div class="jma-actionables"><h3>Account Actionables</h3><div class="jma-action-grid">
        <div>${statusPill("Extend Account", "good")}<p>Balance exists but activity needs protection.</p></div>
        <div>${statusPill("Call Before Expiry", "warn")}<p>Low balance or low activity needs a commercial call.</p></div>
        <div>${statusPill("Delete / Close", "danger")}<p>Zero balance and no activity candidates should be reviewed before closure.</p></div>
        <div>${statusPill("Keep Active", "info")}<p>Regular activity accounts stay under monitoring.</p></div>
      </div></div>`;
    bindReportControls(body);
  }



  function toGatewayRows(companies) {
    return (companies || []).map(c => ({
      companyName: c.companyName || c.company || "",
      company: c.companyName || c.company || "",
      companyId: c.companyId || "",
      obBalance: c.obBalance || 0,
      pbBalance: c.pbBalance || 0,
      orderType: c.orderType || "",
      smsTargetDelivery: c.smsTargetDelivery || 0,
      smsDeliveryThisMonth: c.smsDeliveryThisMonth || 0,
      forwardBooking: c.forwardBooking || 0,
      thisMonthSales: c.thisMonthSales || c.monthlySales || 0,
      monthlySales: c.thisMonthSales || c.monthlySales || 0,
      ytdSales: c.ytdSales || 0,
      yearlyTarget: c.yearlyTarget || 0,
      lastNoteDate: c.lastNoteDate || "",
      risks: c.risks || [],
      flags: (c.risks || []).join("\n"),
      approvedLinks: c.approvedLinks || []
    }));
  }

  function currentChatPayload(body, question) {
    const scoped = getScopedCompanies(body);
    return {
      screen: "sales-report",
      question,
      scope: scoped.scope,
      selectedCompany: scoped.scope === "selected" ? scoped.selected?.companyName : null,
      rows: toGatewayRows(scoped.companies),
      pageInfo: window.JorMallSMAParser.getPageInfo(),
      summaryStats: window.JorMallSMAParser.getSummaryStats(),
      screenshotDelayMs: REPORT_SCREEN_CAPTURE_DELAY_MS
    };
  }

  async function runAIChatbot(body) {
    const input = body.querySelector("#jma-chat-input");
    const output = body.querySelector("#jma-chat-output");
    const prompt = (input?.value || "").trim();
    if (!prompt) {
      output.innerHTML = `<p class="jma-muted">Choose a suggestion or type a question first.</p>`;
      return;
    }

    if (isClientListQuestion(prompt)) {
      const allCompanies = getCompaniesAndStats().companies;
      await showClientListWorkbookPrompt(output, allCompanies, prompt);
      return;
    }

    output.innerHTML = `<div class="jma-chat-answer"><strong>Thinking...</strong><p>Sending the current SMA dataset to the AI Gateway.</p></div>`;

    try {
      const response = await apiFetch(API_CHAT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(currentChatPayload(body, prompt))
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || `Gateway returned HTTP ${response.status}`);
      output.innerHTML = `
        <div class="jma-chat-answer">
          <strong>AI Response ${data.model ? `· ${escapeHtml(data.model)}` : ""}</strong>
          <div class="jma-markdown">${formatMarkdown(data.answer || "No answer returned from the AI Gateway.")}</div>
          <div class="jma-kv"><span>Mode</span><strong>${escapeHtml(data.mode || "openai")}</strong></div>
          <div class="jma-kv"><span>Scope</span><strong>${escapeHtml(data.report?.scope || "all")}</strong></div>
          <div class="jma-kv"><span>Companies analyzed</span><strong>${escapeHtml(data.report?.companiesAnalyzed ?? "-")}</strong></div>
        </div>`;
    } catch (error) {
      output.innerHTML = `
        <div class="jma-chat-answer jma-error-box">
          <strong>AI Gateway Error</strong>
          <p>${escapeHtml(error.message)}</p>
          <p class="jma-muted">Check that the Flask backend is running on ${escapeHtml(API_GATEWAY_BASE_URL)} and that Chrome extension host permissions include the same host.</p>
        </div>`;
    }
  }

  async function refreshGatewayStatus(body, attempt = 0) {
    const status = body.querySelector("#jma-gateway-status");
    const model = body.querySelector("#jma-gateway-model");
    if (!status) return;
    status.textContent = "Checking...";
    try {
      const response = await apiFetch(API_GATEWAY_URL);
      const data = await response.json();
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const gatewayOnline = response.ok && data.ok !== false && String(data.status || "online").toLowerCase() !== "offline";
      const authenticationEnabled = data.authenticationEnabled ?? data.authentication_enabled ?? false;
      const authenticationAccepted = data.authenticationAccepted ?? data.authentication_accepted ?? !authenticationEnabled;
      if (gatewayOnline && authenticationEnabled && !authenticationAccepted) {
        status.textContent = "Gateway online · AI authorization unavailable";
        if (model) model.textContent = data.model || "-";
        return;
      }
      const openaiEnabled = data.openaiEnabled ?? data.openai_enabled ?? gatewayOnline;
      status.textContent = gatewayOnline
        ? (openaiEnabled ? "Connected · AI ready" : "Gateway online · AI unavailable")
        : "Not connected";
      if (model) model.textContent = data.model || (openaiEnabled ? "Active" : "-");
    } catch (error) {
      if (attempt < 2) {
        status.textContent = "Connecting…";
        window.setTimeout(() => refreshGatewayStatus(body, attempt + 1), 1500 * (attempt + 1));
      } else {
        status.textContent = "Not connected · Retry";
      }
      if (model) model.textContent = "-";
    }
  }

  function drawSalesReportBody() {
    const body = document.querySelector(`#${PANEL_ID} .jma-body`);
    if (!body) return;
    const { companies, totals, risks } = getCompaniesAndStats();
    body.innerHTML = `
      <div class="jma-card jma-reports-card jma-leading-report">
        <div class="jma-userbar jma-report-leadbar">
          <div><strong>Executive Report · Allocated Companies</strong><span>SMA user already authenticated · read-only local analysis</span></div>
          <button id="jma-refresh-all" type="button">Refresh</button>
        </div>

        <div class="jma-grid jma-leading-grid">
          ${statCard("Active Companies", companies.length, "companies")}
          ${statCard("Total Balance", (totals.ob + totals.pb).toLocaleString(), "SMS")}
          ${statCard(`SMS Target Delivery — ${getPageMonthYearLabel()}`, totals.target.toLocaleString(), "SMS")}
          ${statCard(`SMS Delivery — ${getPageMonthYearLabel()}`, totals.delivery.toLocaleString(), "SMS")}
        </div>

        <div class="jma-executive-header-row">
          <div>
            <h3>📊 Executive Reports</h3>
            <p class="jma-muted">Default report table is ALL COMPANIES — NORMAL FILTER APPLICATION. Use the Managerial and Sales Executive collapsible screens to expand only the details needed below.</p>
          </div>
        </div>
      </div>

      <button class="jma-button secondary jma-wide-collapse-toggle jma-managerial-wide-toggle" id="jma-toggle-managerial-screen" type="button" aria-expanded="false"><span class="jma-toggle-arrow">▼</span><span>Managerial Screen — Expand</span></button>

      <button class="jma-button secondary jma-wide-collapse-toggle jma-sales-executive-wide-toggle" id="jma-toggle-sales-executive-screen" type="button" aria-expanded="false"><span class="jma-toggle-arrow">▼</span><span>Sales Executive Screen — Expand</span></button>

      <div id="jma-executive-details" class="jma-executive-details jma-card jma-reports-card jma-hidden">
        <div id="jma-mode-badge" class="jma-mode-badge">Executive Mode: Allocated / All Companies</div>

        <div class="jma-report-toolbar">
          <div class="jma-toolbar-grid">
            <div>
              <h3 class="jma-toolbar-header">Analysis Scope</h3>
              <label>Analysis Scope</label>
              <select class="jma-input" id="jma-analysis-scope">
                <option value="all" selected>Allocated Companies (Default)</option>
                <option value="selected">Selected Company</option>
              </select>
            </div>
            <div id="jma-company-select-wrap" style="display:none">
              <label>Selected Company</label>
              <select class="jma-input" id="jma-company-select"></select>
            </div>
          </div>
          <div class="jma-managerial-report-label">Annual Targets and Sales Report</div>
          <div class="jma-report-buttons">
            <button class="jma-button" id="jma-refresh-report">Refresh Analysis</button>
          </div>
        </div>
        <div id="jma-report-output"></div>
      </div>

      <div id="jma-sales-executive-screen" class="jma-sales-executive-screen jma-card jma-reports-card jma-hidden">
        <div id="jma-sales-executive-content"></div>
      </div>

      <div class="jma-card jma-chat-card">
        <h3>AI Chatbot</h3>
        <p class="jma-muted">Ask about the current SMA dataset. The answer is generated by the AI Gateway, not a local preview.</p>
        <div class="jma-prompt-row">
          <button class="jma-prompt" data-prompt="Summarize the delivery issues ATT, BT, Slow Sent, and To Call from this SMA page.">Delivery issues</button>
          <button class="jma-prompt" data-prompt="Which companies should I contact first today and why?">Who to contact</button>
        </div>
        <textarea class="jma-chat-input" id="jma-chat-input" rows="3" placeholder="Ask the assistant about this SMA report..."></textarea>
        <button class="jma-button" id="jma-run-chat" type="button">Ask AI</button>
        <div id="jma-chat-output"></div>
      </div>

      <div class="jma-card jma-gateway-card">
        <h3>API Gateway</h3>
        <p class="jma-muted">Live connection status from the Flask AI Gateway.</p>
        <div class="jma-kv"><span>Status</span><strong id="jma-gateway-status">Checking...</strong></div>
        <div class="jma-kv"><span>Model</span><strong id="jma-gateway-model">-</strong></div>
        <a class="jma-gateway-link" href="${API_GATEWAY_URL}" target="_blank" rel="noopener">Open API Gateway Health Check</a>
      </div>`;

    populateCompanySelector(body, companies);
    syncScopeUi(body);
    body.querySelector("#jma-refresh-all").addEventListener("click", () => drawBody());
    body.querySelector("#jma-analysis-scope").addEventListener("change", () => { syncScopeUi(body); drawExecutiveReports(body); });
    body.querySelector("#jma-company-select").addEventListener("change", () => { drawExecutiveReports(body); });
    body.querySelector("#jma-report-type")?.addEventListener("change", () => drawExecutiveReports(body));
    body.querySelector("#jma-refresh-report").addEventListener("click", () => {
      drawExecutiveReports(body);
    });
    body.querySelector("#jma-toggle-managerial-screen").addEventListener("click", () => {
      executiveManagerialHidden = !executiveManagerialHidden;
      syncManagerialScreenToggle(body);
    });
    body.querySelector("#jma-toggle-sales-executive-screen").addEventListener("click", () => {
      salesExecutiveHidden = !salesExecutiveHidden;
      syncSalesExecutiveScreenToggle(body);
    });
    drawExecutiveReports(body);
    renderSalesExecutiveScreen(body, companies);
    syncManagerialScreenToggle(body);
    syncSalesExecutiveScreenToggle(body);
    refreshGatewayStatus(body);
    body.querySelector("#jma-run-chat").addEventListener("click", () => runAIChatbot(body));
    body.querySelectorAll(".jma-prompt").forEach(btn => {
      btn.addEventListener("click", () => {
        const input = body.querySelector("#jma-chat-input");
        input.value = btn.getAttribute("data-prompt") || "";
        runAIChatbot(body);
      });
    });
  }


  function getCurrentSmaScreen() {
    const href = sourceUrl().toLowerCase();
    // Keep the assistant scoped to screens where it has dedicated logic.
    // Supports http/https and query strings, but does not show on unrelated SMA pages.
    if (/\/sma\/salesassignedsmsuserrep\.cfm(?:[?#]|$)/i.test(href)) return "sales-report";
    if (/\/sma\/noteslistviewallocate\.cfm(?:[?#]|$)/i.test(href)) return "company-notes";
    if (/\/sma\/categorymonthlydeliverynewreport\.cfm(?:[?#]|$)/i.test(href)) return "category-monthly-delivery";
    return "unsupported";
  }
  function isSupportedSmaScreen() {
    return getCurrentSmaScreen() !== "unsupported";
  }

  const NOTE_DEPARTMENTS = [
    "Financial Dept.",
    "Order Processing Dept.",
    "Technical Dept.",
    "Customer Care.",
    "CC. Elite Customers.",
    "Dealers Team. ( Farah Awad )",
    "Retail Department. ( Ghaleb Hasweh )",
    "Sales Team. ( Mohammad Ghaith )",
    "Expired Orders. ( Linda Najjar )",
    "Office Manager ( Tamara Alqatawneh )",
    "SMA Admin ( Maha Mousaui ).",
    "Managment ( Jad )",
    "Miscellaneous"
  ];

  const EMPLOYEE_DEPARTMENT_MAP = {
    "alaa khaireddin": "Financial Dept.",
    "alaa khaireddin.": "Financial Dept.",
    "customer care": "Customer Care.",
    "dania kettaneh": "Customer Care.",
    "deema elkhatib": "Customer Care.",
    "almiral shtaiwi": "Customer Care.",
    "linda najjar": "Expired Orders. ( Linda Najjar )",
    "hawazen abudukhan": "Order Processing Dept.",
    "hiba arabiyat": "Order Processing Dept.",
    "luma saleh": "Order Processing Dept.",
    "maan al-khazzaale": "Order Processing Dept.",
    "maan al-khazzaale": "Order Processing Dept.",
    "farah awad": "Dealers Team. ( Farah Awad )",
    "jad makdah": "Managment ( Jad )",
    "jad": "Managment ( Jad )",
    "maha mousaui": "SMA Admin ( Maha Mousaui ).",
    "tamara alqatawneh": "Office Manager ( Tamara Alqatawneh )"
  };

  function normalizeEmployeeName(value) {
    return String(value || "")
      .replace(/\s+/g, " ")
      .replace(/[()]/g, "")
      .trim()
      .toLowerCase();
  }

  function normalizeDepartment(value) {
    const text = String(value || "").replace(/department$/i, "Dept.").replace(/\s+/g, " ").trim();
    const lower = text.toLowerCase();
    if (!lower) return "Miscellaneous";
    if (/accounting|financial|finance/.test(lower)) return "Financial Dept.";
    if (/order processing|o\.p/.test(lower)) return "Order Processing Dept.";
    if (/technical|tech/.test(lower)) return "Technical Dept.";
    if (/customer care|cc department/.test(lower)) return "Customer Care.";
    if (/elite/.test(lower)) return "CC. Elite Customers.";
    if (/dealer/.test(lower) || /farah awad/.test(lower)) return "Dealers Team. ( Farah Awad )";
    if (/retail|ghaleb/.test(lower)) return "Retail Department. ( Ghaleb Hasweh )";
    if (/sales team|mohammad ghaith/.test(lower)) return "Sales Team. ( Mohammad Ghaith )";
    if (/expired/.test(lower) || /linda najjar/.test(lower)) return "Expired Orders. ( Linda Najjar )";
    if (/office manager|tamara/.test(lower)) return "Office Manager ( Tamara Alqatawneh )";
    if (/sma admin|maha/.test(lower)) return "SMA Admin ( Maha Mousaui ).";
    if (/management|managment|jad/.test(lower)) return "Managment ( Jad )";
    return NOTE_DEPARTMENTS.find(d => d.toLowerCase() === lower) || "Miscellaneous";
  }

  function noteDepartment(note) {
    const raw = String(note.department || "").trim();
    if (raw && normalizeDepartment(raw) !== "Miscellaneous") return normalizeDepartment(raw);

    const person = normalizeEmployeeName(note.addedBy);
    if (EMPLOYEE_DEPARTMENT_MAP[person]) return EMPLOYEE_DEPARTMENT_MAP[person];

    const text = `${note.addedBy || ""} ${note.notice || ""}`.toLowerCase();
    if (/payment|invoice|balance|collected|accounting|finance|po|financial/.test(text)) return "Financial Dept.";
    if (/technical|api|gateway|platform issue|slow platform|sender approval|support/.test(text)) return "Technical Dept.";
    if (/booking|sms content|send sms|campaign|order processing|delivery|sender|otp|srv|adv|order id|target/.test(text)) return "Order Processing Dept.";
    if (/dealer|farah/.test(text)) return "Dealers Team. ( Farah Awad )";
    if (/sales team|sales/.test(text)) return "Sales Team. ( Mohammad Ghaith )";
    if (/expired|expiry|contract will expire|renewal/.test(text)) return "Expired Orders. ( Linda Najjar )";
    if (/talked|called|whatsapp|offer|meeting|follow|contract|renewal|commercial|customer care|not interested|reminder|voice note|sent to/.test(text)) return "Customer Care.";
    return "Miscellaneous";
  }

  function keywordCount(notes, regex) {
    return notes.filter(n => regex.test((n.notice || "").toLowerCase())).length;
  }

  function analyzeCompanyNotesData() {
    const data = window.JorMallSMAParser.extractCompanyNotes();
    const notes = [...(data.notes || [])].sort((a, b) => String(b.iso).localeCompare(String(a.iso)));
    const payments = notes.filter(n => /payment|invoice|balance|collected/.test((n.notice || "").toLowerCase()));
    const clearedPayments = payments.filter(n => /balance\s+(?:for this invoice is\s+)?0\.000|total balance for this client is\s+0\.000/.test((n.notice || "").toLowerCase()));
    const paymentAttitude = payments.length && clearedPayments.length >= Math.ceil(payments.length * 0.6)
      ? "Pays well / usually clears balances"
      : payments.length ? "Payment behavior needs finance follow-up" : "No clear payment pattern detected";

    const unreachable = keywordCount(notes, /no luck|couldn`t reach|couldn't reach|didn.?t answer|not answering|unresponsive/);
    const replies = keywordCount(notes, /replied|sent|called|met|signed|requested|will get back|got back|meeting|whatsapp/);
    const recent90 = notes.filter(n => n.iso && (Date.now() - new Date(n.iso).getTime()) <= 90 * 24 * 60 * 60 * 1000);
    const responseAttitude = unreachable >= 3 ? "Slow / sometimes hard to reach" : replies >= 5 ? "Responsive when followed up" : "Mixed response speed";

    const departmentMap = {};
    notes.forEach(n => {
      const cat = noteDepartment(n);
      departmentMap[cat] = departmentMap[cat] || [];
      departmentMap[cat].push(n);
    });

    return { ...data, notes, payments, clearedPayments, paymentAttitude, responseAttitude, recent90, departmentMap };
  }

  function renderNoteRows(notes, limit = 8) {
    return notes.slice(0, limit).map(n => `
      <tr>
        <td>${escapeHtml(n.rawDate || "-")}</td>
        <td>${escapeHtml(n.addedBy || "-")}</td>
        <td>${escapeHtml(noteDepartment(n))}</td>
        <td>${escapeHtml(n.notice || "-")}</td>
      </tr>`).join("\n") || `<tr><td colspan="4">No notes detected.</td></tr>`;
  }

  function latestNote(departmentMap, department) {
    return ((departmentMap && departmentMap[department]) || [])[0] || null;
  }

  function renderTeamSteps(departmentMap) {
    const teams = [
      ["Financial Dept.", "Confirm current balance, last invoice status, and whether any collection reminder is needed."],
      ["Order Processing Dept.", "Check active bookings, sender IDs, platform usage, pending delivery, and reporting items."],
      ["Technical Dept.", "Verify API/platform issues, sender approval, delivery reports, and technical blockers."],
      ["Customer Care.", "Contact the client with one clear reason: renewal, usage follow-up, or issue closure."],
      ["CC. Elite Customers.", "Review VIP/elite handling requirements and escalate relationship risks."],
      ["Dealers Team. ( Farah Awad )", "Review dealer-related bookings, follow-up, and reseller handling."],
      ["Retail Department. ( Ghaleb Hasweh )", "Review retail opportunity, renewal timing, and conversion follow-up."],
      ["Sales Team. ( Mohammad Ghaith )", "Review sales opportunity, renewal value, and next offer."],
      ["Expired Orders. ( Linda Najjar )", "Review expiry, renewal deadline, and extension/renewal action."],
      ["Office Manager ( Tamara Alqatawneh )", "Review administrative follow-up or internal coordination needed."],
      ["SMA Admin ( Maha Mousaui ).", "Confirm SMA ownership, allocation, and missing account data updates."],
      ["Managment ( Jad )", "Escalate strategic accounts, stuck accounts, or exceptional commercial decisions."],
      ["Miscellaneous", "Review notes that did not include a clear department and assign ownership if needed."]
    ];
    const existingTeams = teams
      .map(([team, fallback]) => ({ team, fallback, latest: latestNote(departmentMap, team), count: ((departmentMap && departmentMap[team]) || []).length }))
      .filter(item => item.count > 0 && item.latest);
    if (!existingTeams.length) return `<p class="jma-muted">No department-owned current steps detected from these notes.</p>`;
    return existingTeams.map(({ team, latest, count }) => {
      return `<div class="jma-team-row"><strong>${escapeHtml(team)}</strong><span>${count} note(s)</span><p>${escapeHtml(latest.notice || "No step detected.")}</p></div>`;
    }).join("\n");
  }

  function renderDepartmentSummary(departmentMap) {
    const entries = NOTE_DEPARTMENTS
      .map(department => [department, (departmentMap && departmentMap[department]) || []])
      .filter(([, rows]) => rows.length)
      .sort((a, b) => (b[1] || []).length - (a[1] || []).length);
    if (!entries.length) return `<p class="jma-muted">No department notes detected yet.</p>`;
    return `<div class="jma-department-compact">${entries.map(([department, rows]) => {
      const latest = (rows || [])[0] || {};
      return `<div class="jma-department-line"><div><strong>${escapeHtml(department)}</strong><span>${(rows || []).length} note(s)</span></div><p>${escapeHtml(latest.notice || "No latest note detected.")}</p></div>`;
    }).join("\n")}</div>`;
  }

  function notesChatPayload(question) {
    const data = analyzeCompanyNotesData();
    return {
      screen: "company-notes",
      question,
      notesData: data,
      pageInfo: window.JorMallSMAParser.getPageInfo()
    };
  }

  async function runNotesChatbot(body) {
    const input = body.querySelector("#jma-notes-chat-input");
    const output = body.querySelector("#jma-notes-chat-output");
    const prompt = (input?.value || "").trim();
    if (!prompt) {
      output.innerHTML = `<p class="jma-muted">Choose a suggestion or type a notes question first.</p>`;
      return;
    }
    output.innerHTML = `<div class="jma-chat-answer"><strong>Thinking...</strong><p>Sending this company notes history to the AI Gateway.</p></div>`;
    try {
      const response = await apiFetch(API_CHAT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(notesChatPayload(prompt))
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || `Gateway returned HTTP ${response.status}`);
      output.innerHTML = `<div class="jma-chat-answer"><strong>AI Response ${data.model ? `· ${escapeHtml(data.model)}` : ""}</strong><div class="jma-markdown">${formatMarkdown(data.answer || "No answer returned from the AI Gateway.")}</div></div>`;
    } catch (error) {
      output.innerHTML = `<div class="jma-chat-answer jma-error-box"><strong>AI Gateway Error</strong><p>${escapeHtml(error.message)}</p><p class="jma-muted">Check that the Flask backend is running on ${escapeHtml(API_GATEWAY_BASE_URL)}.</p></div>`;
    }
  }

  function normalizeDepartmentText(cat, fallbackMap) {
    const source = (cat && Object.keys(cat || {}).length) ? cat : fallbackMap;
    if (typeof source === "string") return source.trim();
    return Object.entries(source || {})
      .filter(([, v]) => {
        if (typeof v === "number") return v > 0;
        if (Array.isArray(v)) return v.length > 0;
        if (v && typeof v === "object") return Number(v.count || 0) > 0 || Boolean(v.latestNote || v.summary || v.text);
        return Boolean(String(v || "").trim());
      })
      .map(([k, v]) => {
        if (Array.isArray(v)) return `**${k}:** ${v.length} note(s)${v[0]?.notice ? ` — ${v[0].notice}` : ""}`;
        if (typeof v === "number") return `**${k}:** ${v} note(s)`;
        if (v && typeof v === "object") return `**${k}:** ${v.count || ""} note(s)${v.latestNote ? ` — ${v.latestNote}` : v.summary ? ` — ${v.summary}` : ""}`;
        return `**${k}:** ${v}`;
      }).join("\n");
  }

  function renderAiNotesSummary(data, localAnalysis) {
    if (!data) return "";
    const ai = data.aiSummary || {};
    const executive = ai.executive_summary || data.summary || "Waiting for AI notes summary.";
    const latest = ai.latest_updates_summary || "";
    const facts = ai.account_facts || data.accountFacts || {};
    const risks = ai.risks || "";
    const next = ai.next_best_action || ai.suggested_technique || "";
    const rawFallback = ai.raw && !ai.executive_summary ? ai.raw : "";
    const departmentText = normalizeDepartmentText(ai.department_summary || data.departmentSummary || data.departments || data.categories, localAnalysis?.departmentMap);
    const factsText = typeof facts === "string" ? facts : Object.entries(facts || {}).filter(([, v]) => Boolean(v)).map(([k, v]) => `**${k.replace(/_/g, " ")}:** ${v}`).join("\n");
    return `
      <div class="jma-ai-notes-summary">
        <div class="jma-section-title">AI Notes Summary</div>
        <div class="jma-note jma-ai-main"><strong>Executive summary</strong><div class="jma-markdown">${formatMarkdown(rawFallback || executive)}</div></div>
        <div class="jma-ai-two-col">
          ${factsText ? `<div class="jma-note"><strong>Account facts</strong><div class="jma-markdown">${formatMarkdown(factsText)}</div></div>` : ""}
          ${latest ? `<div class="jma-note"><strong>Latest updates</strong><div class="jma-markdown">${formatMarkdown(latest)}</div></div>` : ""}
          ${risks ? `<div class="jma-note"><strong>Risks</strong><div class="jma-markdown">${formatMarkdown(Array.isArray(risks) ? risks.map(r => `- ${r}`).join("\n") : risks)}</div></div>` : ""}
          ${next ? `<div class="jma-note"><strong>Next best action</strong><div class="jma-markdown">${formatMarkdown(next)}</div></div>` : ""}
        </div>
        ${departmentText ? `<details class="jma-details" open><summary>Existing department summary</summary><div class="jma-markdown">${formatMarkdown(departmentText)}</div></details>` : ""}
      </div>`;
  }

  async function loadAINotesSummary(body, localAnalysis) {
    const target = body.querySelector("#jma-ai-notes-summary");
    if (!target) return;
    target.innerHTML = `<div class="jma-loading-card"><div class="jma-spinner"></div><div><strong>Loading AI notes summary...</strong><p>Analyzing notes, payment behavior, response attitude, and team ownership.</p></div></div>`;
    try {
      const response = await apiFetch(`${API_GATEWAY_BASE_URL}/sma/analyze-notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notesData: localAnalysis, pageUrl: sourceUrl() })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || `Gateway returned HTTP ${response.status}`);
      target.innerHTML = renderAiNotesSummary(data, localAnalysis);
    } catch (error) {
      target.innerHTML = `<div class="jma-note jma-error-box"><strong>AI Notes Summary unavailable:</strong><br>${escapeHtml(error.message)}<br><span class="jma-muted">The local department summary remains available below.</span></div>`;
    }
  }

  function drawCompanyNotesBody() {
    const body = document.querySelector(`#${PANEL_ID} .jma-body`);
    if (!body) return;
    const a = analyzeCompanyNotesData();
    const latest = a.notes[0];
    const commercialResistance = keywordCount(a.notes, /not interested in the commercial|commercial campaigns|zain|another company|competition/);
    const platformOnly = keywordCount(a.notes, /platform only|service sms|their data only|platform usage/);
    const technique = commercialResistance
      ? "Do not push generic commercial campaigns first. Lead with service SMS/platform reliability, official reporting, and a small controlled campaign proof."
      : platformOnly
        ? "Position JorMall as the safest platform/service SMS partner, then upsell targeted campaigns after trust is refreshed."
        : "Use a normal renewal and value-based upsell approach with clear next campaign ideas.";

    body.innerHTML = `
      <div class="jma-card jma-notes-card">
        <div class="jma-userbar jma-report-leadbar">
          <div><strong>Company Notes Intelligence</strong><span>URL screen: noteslistviewallocate.cfm · compid ${escapeHtml(a.compid || "-")}</span></div>
          <button id="jma-refresh-notes" type="button">Refresh</button>
        </div>
        <h3>${escapeHtml(a.companyName || "Company History Notes")}</h3>
        <div class="jma-grid jma-leading-grid jma-notes-stats">
          ${statCard("Total Notes", a.notes.length, "notes")}
          ${statCard("Recent 90 Days", a.recent90.length, "notes")}
          ${statCard("Payment Notes", a.payments.length, `${a.clearedPayments.length} cleared`)}
          ${statCard("Latest Update", latest?.rawDate || "-", "date")}
        </div>
        <div class="jma-notes-status-strip">
          <div><span>Payment Attitude</span><strong>${escapeHtml(a.paymentAttitude)}</strong></div>
          <div><span>Response Attitude</span><strong>${escapeHtml(a.responseAttitude)}</strong></div>
          <div><span>Usage / Interest</span><strong>${platformOnly ? "Platform / own data" : commercialResistance ? "Commercial cautious" : "Review needed"}</strong></div>
        </div>
        <div id="jma-ai-notes-summary"></div>
        <div class="jma-note jma-technique"><strong>Suggested technique:</strong><br>${escapeHtml(technique)}</div>
        <div class="jma-notes-two-col">
          <div>
            <div class="jma-section-title">Existing Department Summary</div>
            ${renderDepartmentSummary(a.departmentMap)}
          </div>
          <div>
            <div class="jma-section-title">Current Steps by Team</div>
            <div class="jma-team-compact">${renderTeamSteps(a.departmentMap)}</div>
          </div>
        </div>
        <div class="jma-section-title">Last Updates</div>
        <div class="jma-table-wrap"><table class="jma-report-table jma-notes-table"><thead><tr><th>Date</th><th>Added By</th><th>Department</th><th>Notice</th></tr></thead><tbody>${renderNoteRows(a.notes, 12)}</tbody></table></div>
      </div>

      <div class="jma-card jma-chat-card">
        <h3>Notes Chatbot</h3>
        <p class="jma-muted">Ask about this specific company's notes, payment attitude, response style, next action, or team ownership.</p>
        <div class="jma-prompt-row">
          <button class="jma-notes-prompt" data-prompt="Summarize the customer's latest updates and attitude from these notes.">Latest attitude</button>
          <button class="jma-notes-prompt" data-prompt="What should Financial, Customer Care, Order Processing, Technical, Expired Orders, Sales, and SMA Admin each do next?">Team next steps</button>
          <button class="jma-notes-prompt" data-prompt="Is this customer paying on time and responding fast or slowly?">Payment/response</button>
          <button class="jma-notes-prompt" data-prompt="What technique should we use when contacting this customer?">Best technique</button>
        </div>
        <textarea class="jma-chat-input" id="jma-notes-chat-input" rows="3" placeholder="Ask about this company's notes..."></textarea>
        <button class="jma-button" id="jma-run-notes-chat" type="button">Ask AI</button>
        <div id="jma-notes-chat-output"></div>
      </div>`;
    body.querySelector("#jma-refresh-notes").addEventListener("click", drawCompanyNotesBody);
    body.querySelector("#jma-run-notes-chat").addEventListener("click", () => runNotesChatbot(body));
    body.querySelectorAll(".jma-notes-prompt").forEach(btn => {
      btn.addEventListener("click", () => {
        const input = body.querySelector("#jma-notes-chat-input");
        input.value = btn.getAttribute("data-prompt") || "";
        runNotesChatbot(body);
      });
    });
    loadAINotesSummary(body, a);
  }



  function categoryMonthlyRows() {
    const data = window.JorMallSMAParser.extractCategoryMonthlyDelivery ? window.JorMallSMAParser.extractCategoryMonthlyDelivery() : { rows: [], summaries: [] };
    const rows = (data.rows || []).map(r => ({
      ...r,
      obBalanceNumber: num(r.obBalance),
      pbBalanceNumber: num(r.pbBalance),
      lastYearDeliveryNumber: num(r.lastYearDelivery),
      smsTargetDeliveryNumber: num(r.smsTargetDelivery),
      smsDeliveryThisMonthNumber: num(r.smsDeliveryThisMonth),
      localDeliveryNumber: num(r.localDelivery),
      platformDeliveryNumber: num(r.platformDelivery),
      forwardBookingNumber: num(r.forwardBooking),
      differenceNumber: num(r.difference),
      totalBalanceNumber: num(r.obBalance) + num(r.pbBalance)
    }));
    const summaries = (data.summaries || []).map(r => ({
      ...r,
      orderBalanceNumber: num(r.orderBalance),
      platformBalanceNumber: num(r.platformBalance),
      lastYearDeliveryNumber: num(r.lastYearDelivery),
      targetNumber: num(r.target),
      forwardBookingNumber: num(r.forwardBooking),
      deliveryToDateNumber: num(r.deliveryToDate),
      differenceNumber: num(r.difference),
      totalBalanceNumber: num(r.orderBalance) + num(r.platformBalance)
    }));
    return { rows, summaries, pageInfo: data.pageInfo || window.JorMallSMAParser.getPageInfo() };
  }

  function categoryRowTarget(row) {
    return num(row.smsTargetDeliveryNumber ?? row.targetNumber ?? row.smsTargetDelivery ?? row.target);
  }

  function categoryRowDelivery(row) {
    return num(row.smsDeliveryThisMonthNumber ?? row.deliveryToDateNumber ?? row.smsDeliveryThisMonth ?? row.deliveryToDate);
  }

  function categoryRowBalance(row) {
    return num(row.totalBalanceNumber ?? (num(row.obBalanceNumber ?? row.orderBalanceNumber ?? row.obBalance ?? row.orderBalance) + num(row.pbBalanceNumber ?? row.platformBalanceNumber ?? row.pbBalance ?? row.platformBalance)));
  }

  function categoryRowMessageCount(row) {
    return categoryRowDelivery(row);
  }

  function categoryPlatformType(row) {
    return String(row.platformType || "").trim();
  }

  function categoryPlatformTypeKey(row) {
    const value = categoryPlatformType(row).toLowerCase().replace(/&/g, "and");
    const hasCommercial = /commercial/.test(value);
    const hasService = /service/.test(value);
    if (hasCommercial && hasService) return "both";
    if (hasCommercial) return "commercial";
    if (hasService) return "service";
    return "none";
  }

  function categoryHasPlatformType(row) {
    return categoryPlatformTypeKey(row) !== "none";
  }

  function categoryDisplayBalance(row, kind) {
    const isPb = kind === "pb";
    const value = isPb
      ? num(row.pbBalanceNumber ?? row.platformBalanceNumber ?? row.pbBalance ?? row.platformBalance)
      : num(row.obBalanceNumber ?? row.orderBalanceNumber ?? row.obBalance ?? row.orderBalance);
    if (value !== 0) return fmt(value);
    const hasPlatform = categoryHasPlatformType(row);
    // Requested rule: when there is no Platform Type and PB is 0, show NA.
    // Same display rule is applied to OB when its value is also 0, so empty balances are not mistaken for real zero balances.
    if (!hasPlatform) return `<span class="jma-muted">NA</span>`;
    return `<span class="jma-muted">0</span>`;
  }

  function categoryDisplayTotalBalance(row) {
    return fmt(categoryRowBalance(row));
  }

  function parseSmaDate(value) {
    const text = String(value || "");
    const match = text.match(/(\d{2})\/(\d{2})\/(\d{4})/);
    if (!match) return null;
    const day = Number(match[1]);
    const month = Number(match[2]);
    const year = Number(match[3]);
    if (!day || !month || !year) return null;
    return new Date(year, month - 1, day);
  }

  function isFreeOrder1900(expiryDate) {
    return /\b1900\b/.test(String(expiryDate || ""));
  }

  function isExpiredByDate(expiryDate) {
    if (isFreeOrder1900(expiryDate)) return false;
    const dt = parseSmaDate(expiryDate);
    if (!dt) return false;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    dt.setHours(0, 0, 0, 0);
    return dt < today;
  }

  function categoryDeliveryFilters(rows) {
    const issueFilter = categoryDeliveryState.filter || "all";
    const balanceFilter = categoryDeliveryState.balanceFilter || "all";
    const obBalanceFilter = categoryDeliveryState.obBalanceFilter || "all";
    const pbBalanceFilter = categoryDeliveryState.pbBalanceFilter || "all";
    const platformTypeFilter = categoryDeliveryState.platformTypeFilter || "all";
    const passesBalanceChoice = (value, choice) => {
      if (choice === "zero") return value === 0;
      if (choice === "positive") return value > 0;
      if (choice === "negative") return value < 0;
      return true;
    };
    return rows.filter(r => {
      const target = categoryRowTarget(r);
      const delivery = categoryRowDelivery(r);
      const balance = categoryRowBalance(r);
      const obBalance = num(r.obBalanceNumber ?? r.orderBalanceNumber ?? r.obBalance ?? r.orderBalance);
      const pbBalance = num(r.pbBalanceNumber ?? r.platformBalanceNumber ?? r.pbBalance ?? r.platformBalance);
      let issueOk = true;
      if (issueFilter === "att") issueOk = (r.risks || []).includes("ATT");
      if (issueFilter === "bt") issueOk = (r.risks || []).includes("BT") || num(r.differenceNumber ?? r.difference) < 0;
      if (issueFilter === "slowSent") issueOk = (r.risks || []).includes("Slow Sent");
      if (issueFilter === "toCall") issueOk = (r.risks || []).includes("To Call");
      if (issueFilter === "soon") issueOk = isCompanyExpiringSoon(r);
      // Expired is now based ONLY on the real expiry date.
      // 1900 is treated separately as a Free Order, not as expired.
      if (issueFilter === "expired") issueOk = isExpiredByDate(r.expiryDate);
      if (issueFilter === "free1900") issueOk = isFreeOrder1900(r.expiryDate);
      if (issueFilter === "noDelivery") issueOk = target > 0 && delivery === 0;
      if (issueFilter === "fast") issueOk = target > 0 && delivery >= target;
      const balanceOk = passesBalanceChoice(balance, balanceFilter);
      const obOk = passesBalanceChoice(obBalance, obBalanceFilter);
      const pbOk = passesBalanceChoice(pbBalance, pbBalanceFilter);
      const appliesPlatformFilter = Object.prototype.hasOwnProperty.call(r, "platformType");
      const platformTypeKey = categoryPlatformTypeKey(r);
      const platformOk = !appliesPlatformFilter || platformTypeFilter === "all" || platformTypeKey === platformTypeFilter;
      return issueOk && balanceOk && obOk && pbOk && platformOk;
    });
  }

  function categoryFilteredRows(rows) {
    return categoryDeliveryFilters(rows || []);
  }

  function categoryDisplayedTotals(rows) {
    const filtered = categoryFilteredRows(rows);
    return {
      count: filtered.length,
      totalMessages: filtered.reduce((sum, r) => sum + categoryRowMessageCount(r), 0),
      totalObBalance: filtered.reduce((sum, r) => sum + num(r.obBalanceNumber ?? r.orderBalanceNumber ?? r.obBalance ?? r.orderBalance), 0),
      totalPbBalance: filtered.reduce((sum, r) => sum + num(r.pbBalanceNumber ?? r.platformBalanceNumber ?? r.pbBalance ?? r.platformBalance), 0),
      totalBalance: filtered.reduce((sum, r) => sum + categoryRowBalance(r), 0),
    };
  }

  function categoryBalanceFilterChoices(rows, valueGetter) {
    const hasNegative = (rows || []).some(r => valueGetter(r) < 0);
    const choices = [["all", "All"], ["zero", "Zero"], ["positive", "Positive"]];
    if (hasNegative) choices.push(["negative", "Negative"]);
    return choices;
  }

  function categoryBalanceFilterGroupHtml(rows, title, stateKey, dataAttr, valueGetter) {
    const choices = categoryBalanceFilterChoices(rows, valueGetter);
    return `<div class="jma-balance-filter-group">
      <span>${escapeHtml(title)}</span>
      <div class="jma-filter-row jma-category-balance-filter-row">
        ${choices.map(([key,label]) => `<button type="button" class="jma-filter-chip ${categoryDeliveryState[stateKey] === key ? "active" : ""}" ${dataAttr}="${key}" title="${key === "zero" ? title + " equals 0" : key === "positive" ? title + " is greater than 0" : key === "negative" ? title + " is less than 0" : "Show all " + title}">${escapeHtml(label)}</button>`).join("")}
      </div>
    </div>`;
  }

  function categoryPlatformTypeFiltersHtml(rows) {
    const counts = (rows || []).reduce((acc, row) => {
      const key = categoryPlatformTypeKey(row);
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, { all: (rows || []).length });
    const choices = [["all", "All"], ["commercial", "Commercial"], ["service", "Service"], ["both", "Both"], ["none", "No Platform Type"]];
    return `<div class="jma-balance-filter-panel jma-platform-filter-panel">
      <div class="jma-balance-filter-group">
        <span>Platform Type</span>
        <div class="jma-filter-row jma-category-platform-filter-row">
          ${choices.map(([key,label]) => `<button type="button" class="jma-filter-chip ${categoryDeliveryState.platformTypeFilter === key ? "active" : ""}" data-category-platform-type-filter="${key}" title="${escapeHtml(label)} platform type rows">${escapeHtml(label)} <small>${counts[key] || 0}</small></button>`).join("")}
        </div>
      </div>
    </div>`;
  }

  function categoryBalanceFiltersHtml(rows) {
    return `<div class="jma-balance-filter-panel">
      ${categoryBalanceFilterGroupHtml(rows, "Total Balance", "balanceFilter", "data-category-balance-filter", categoryRowBalance)}
      ${categoryBalanceFilterGroupHtml(rows, "OB Balance", "obBalanceFilter", "data-category-ob-balance-filter", r => num(r.obBalanceNumber ?? r.orderBalanceNumber ?? r.obBalance ?? r.orderBalance))}
      ${categoryBalanceFilterGroupHtml(rows, "PB Balance", "pbBalanceFilter", "data-category-pb-balance-filter", r => num(r.pbBalanceNumber ?? r.platformBalanceNumber ?? r.pbBalance ?? r.platformBalance))}
    </div>`;
  }

  function categoryDeliveryStatus(row) {
    const combined = [];
    if (isFreeOrder1900(row.expiryDate)) combined.push("Free Order");
    else if (isExpiredByDate(row.expiryDate)) combined.push("Expired");
    if ((row.risks || []).includes("BT") || row.differenceNumber < 0) combined.push("BT");
    if ((row.risks || []).includes("Slow Sent")) combined.push("Slow Sent");
    if ((row.risks || []).includes("ATT")) combined.push("ATT");
    if ((row.risks || []).includes("To Call")) combined.push("To Call");
    if (combined.length) return { label: combined.join("/"), cls: combined.includes("Expired") || combined.includes("ATT") || combined.includes("BT") ? "danger" : "warn" };
    if (categoryRowTarget(row) > 0 && categoryRowDelivery(row) >= categoryRowTarget(row)) return { label: "Fast", cls: "good" };
    return { label: "On Track", cls: "info" };
  }

  function sortCategoryRows(rows, columns) {
    const key = categoryDeliveryState.sortKey || columns[0]?.key;
    const direction = categoryDeliveryState.direction || "desc";
    const col = columns.find(c => c.key === key) || columns[0] || { type: "text" };
    return [...rows].sort((a,b) => {
      const av = col.type === "number" ? num(a[key]) : String(a[key] ?? "").toLowerCase();
      const bv = col.type === "number" ? num(b[key]) : String(b[key] ?? "").toLowerCase();
      const result = av > bv ? 1 : av < bv ? -1 : 0;
      return direction === "asc" ? result : -result;
    });
  }

  function categoryCompanyCell(row) {
    const name = escapeHtml(row.companyName || "-");
    const id = row.companyId || "";
    return id ? `<a class="jma-company-link" href="http://sma/sma/ActiveOrderReport.cfm?compid=${encodeURIComponent(id)}" target="_blank" rel="noopener">${name}</a>` : name;
  }

  function categoryTableHtml(rows, columns, limitKey) {
    const filtered = categoryDeliveryFilters(rows);
    const sorted = sortCategoryRows(filtered, columns);
    const limit = getRankingLimit(limitKey);
    const shown = sorted.slice(0, limit);
    const arrow = (key) => categoryDeliveryState.sortKey === key ? (categoryDeliveryState.direction === "asc" ? "↑" : "↓") : "↕";
    return `
      <div class="jma-limit-controls" data-limit-key="${escapeHtml(limitKey)}">
        <span>Results: ${Math.min(shown.length, sorted.length)} of ${sorted.length}</span>
        ${RESULT_LIMIT_CHOICES.map(choice => `<button type="button" class="jma-limit-btn ${limit === choice ? "active" : ""}" data-limit="${choice}">${choice}</button>`).join("")}
        <button type="button" class="jma-limit-btn ${limit >= 999999 ? "active" : ""}" data-limit="999999">Max</button>
        <input class="jma-limit-custom" type="number" min="1" placeholder="Custom" value="${RESULT_LIMIT_CHOICES.includes(limit) || limit >= 999999 ? "" : limit}">
        <button type="button" class="jma-limit-apply">Apply</button>
      </div>
      <div class="jma-table-wrap"><table class="jma-report-table jma-report-subtable"><thead><tr>
        <th>#</th>${columns.map(col => `<th><button type="button" class="jma-category-sort-btn" data-sort-key="${escapeHtml(col.key)}">${escapeHtml(col.label)} <span>${arrow(col.key)}</span></button></th>`).join("")}
      </tr></thead><tbody>
        ${shown.map((row, i) => `<tr><td>${i + 1}</td>${columns.map(col => `<td class="${col.className ? col.className(row) : ""}">${col.render(row)}</td>`).join("")}</tr>`).join("") || `<tr><td colspan="${columns.length + 1}">No rows found.</td></tr>`}
      </tbody></table></div>`;
  }


  function bindCategoryLimitControls(body) {
    body.querySelectorAll('.jma-limit-controls[data-limit-key^="category"]').forEach(wrap => {
      const key = wrap.getAttribute("data-limit-key") || "categoryCustomers";
      const setLimitAndRefresh = (value) => {
        const next = Number(value);
        rankingLimitState[key] = Number.isFinite(next) && next > 0 ? next : DEFAULT_RANKING_LIMIT;
        // Re-render the active Category Monthly Delivery screen. This works for BOTH tables:
        // categoryCustomers and categorySummary.
        drawCategoryMonthlyDeliveryBody();
      };
      wrap.querySelectorAll(".jma-limit-btn").forEach(btn => {
        btn.addEventListener("click", event => {
          event.preventDefault();
          event.stopPropagation();
          setLimitAndRefresh(btn.getAttribute("data-limit"));
        });
      });
      const apply = () => {
        const input = wrap.querySelector(".jma-limit-custom");
        const value = Math.max(1, Number(input?.value || 0));
        if (Number.isFinite(value) && value > 0) setLimitAndRefresh(value);
      };
      wrap.querySelector(".jma-limit-apply")?.addEventListener("click", event => {
        event.preventDefault();
        event.stopPropagation();
        apply();
      });
      wrap.querySelector(".jma-limit-custom")?.addEventListener("keydown", event => {
        if (event.key === "Enter") {
          event.preventDefault();
          event.stopPropagation();
          apply();
        }
      });
    });
  }

  function categoryMonthlyChatPayload(question) {
    const data = categoryMonthlyRows();
    const selectedRows = categoryDeliveryState.table === "summary" ? data.summaries : data.rows;
    const filteredRows = categoryFilteredRows(selectedRows);
    return {
      screen: "category-monthly-delivery",
      question,
      table: categoryDeliveryState.table,
      issueFilter: categoryDeliveryState.filter,
      balanceFilter: categoryDeliveryState.balanceFilter,
      obBalanceFilter: categoryDeliveryState.obBalanceFilter,
      pbBalanceFilter: categoryDeliveryState.pbBalanceFilter,
      platformTypeFilter: categoryDeliveryState.platformTypeFilter,
      categoryDeliveryData: {
        rows: data.rows.slice(0, 250),
        summaries: data.summaries,
        filteredRows: filteredRows.slice(0, 250),
        displayedTotals: categoryDisplayedTotals(selectedRows),
      },
      pageInfo: window.JorMallSMAParser.getPageInfo(),
      pageUrl: sourceUrl(),
    };
  }

  async function runCategoryChatbot(body) {
    const input = body.querySelector("#jma-category-chat-input");
    const output = body.querySelector("#jma-category-chat-output");
    const prompt = (input?.value || "").trim();
    if (!prompt) {
      output.innerHTML = `<p class="jma-muted">Choose a suggestion or type a question first.</p>`;
      return;
    }
    if (isClientListQuestion(prompt)) {
      const allRows = categoryMonthlyRows().rows;
      await showClientListWorkbookPrompt(output, allRows, prompt);
      return;
    }
    output.innerHTML = `<div class="jma-chat-answer"><strong>Thinking...</strong><p>Sending the currently displayed category delivery table to the AI Gateway.</p></div>`;
    try {
      const response = await apiFetch(API_CHAT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(categoryMonthlyChatPayload(prompt))
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || `Gateway returned HTTP ${response.status}`);
      output.innerHTML = `<div class="jma-chat-answer"><strong>AI Response ${data.model ? `· ${escapeHtml(data.model)}` : ""}</strong><div class="jma-markdown">${formatMarkdown(data.answer || "No answer returned from the AI Gateway.")}</div></div>`;
    } catch (error) {
      output.innerHTML = `<div class="jma-chat-answer jma-error-box"><strong>AI Gateway Error</strong><p>${escapeHtml(error.message)}</p><p class="jma-muted">Check that the Flask backend is running on ${escapeHtml(API_GATEWAY_BASE_URL)}.</p></div>`;
    }
  }

  function drawCategoryMonthlyDeliveryBody() {
    const body = document.querySelector(`#${PANEL_ID} .jma-body`);
    if (!body) return;
    const data = categoryMonthlyRows();
    const rows = data.rows;
    const summaries = data.summaries;
    const totalTarget = rows.reduce((s, r) => s + r.smsTargetDeliveryNumber, 0);
    const totalDelivery = rows.reduce((s, r) => s + r.smsDeliveryThisMonthNumber, 0);
    const totalDiff = rows.reduce((s, r) => s + r.differenceNumber, 0);
    const btCount = rows.filter(r => (r.risks || []).includes("BT") || r.differenceNumber < 0).length;
    const callCount = rows.filter(r => (r.risks || []).includes("To Call")).length;
    const noDelivery = rows.filter(r => r.smsTargetDeliveryNumber > 0 && r.smsDeliveryThisMonthNumber === 0).length;
    const selectedTable = categoryDeliveryState.table || "customers";
    const tableRows = selectedTable === "summary" ? summaries : rows;
    const displayedTotals = categoryDisplayedTotals(tableRows);
    const customerColumns = [
      { key: "seName", label: "SE / Department", type: "text", render: r => escapeHtml(`${r.seCode || "-"} · ${r.seName || "-"}`) },
      { key: "companyName", label: "Customer", type: "text", render: categoryCompanyCell },
      { key: "platformType", label: "Platform Type", type: "text", render: r => escapeHtml(r.platformType || "-") },
      { key: "expiryDate", label: "Expiry", type: "text", render: r => escapeHtml(r.expiryDate || "-") },
      { key: "obBalanceNumber", label: "OB Balance (SMS)", type: "number", render: r => categoryDisplayBalance(r, "ob"), className: balanceClass },
      { key: "pbBalanceNumber", label: "PB Balance (SMS)", type: "number", render: r => categoryDisplayBalance(r, "pb"), className: balanceClass },
      { key: "totalBalanceNumber", label: "Total Balance (SMS)", type: "number", render: r => categoryDisplayTotalBalance(r), className: balanceClass },
      { key: "smsTargetDeliveryNumber", label: `Target — ${getPageMonthYearLabel()}`, type: "number", render: r => fmt(r.smsTargetDeliveryNumber) },
      { key: "smsDeliveryThisMonthNumber", label: `Delivery To Date — ${getPageMonthYearLabel()}`, type: "number", render: r => `LD ${fmt(r.localDeliveryNumber)}<br>PD ${fmt(r.platformDeliveryNumber)}<br><strong>TD ${fmt(r.smsDeliveryThisMonthNumber)}</strong>` },
      { key: "differenceNumber", label: "Difference", type: "number", render: r => `<span class="${r.differenceNumber >= 0 ? "jma-good-text" : "jma-danger-text"}">${fmt(r.differenceNumber)}</span>` },
      { key: "risk", label: "Delivery Risk", type: "text", render: r => { const st = categoryDeliveryStatus(r); return statusPill(st.label, st.cls); } },
      { key: "lastNoteDate", label: "Last Note", type: "text", render: r => escapeHtml(r.lastNoteDate || "-") }
    ];
    const summaryColumns = [
      { key: "seName", label: "SE / Category", type: "text", render: r => escapeHtml(`${r.seCode || "-"} · ${r.seName || "-"}`) },
      { key: "orderBalanceNumber", label: "OB Balance (SMS)", type: "number", render: r => fmt(r.orderBalanceNumber) },
      { key: "platformBalanceNumber", label: "PB Balance (SMS)", type: "number", render: r => fmt(r.platformBalanceNumber) },
      { key: "totalBalanceNumber", label: "Total Balance (SMS)", type: "number", render: r => fmt(r.totalBalanceNumber) },
      { key: "targetNumber", label: `Target — ${getPageMonthYearLabel()}`, type: "number", render: r => fmt(r.targetNumber) },
      { key: "forwardBookingNumber", label: "Forward Booking", type: "number", render: r => fmt(r.forwardBookingNumber) },
      { key: "deliveryToDateNumber", label: `Delivery To Date — ${getPageMonthYearLabel()}`, type: "number", render: r => fmt(r.deliveryToDateNumber) },
      { key: "differenceNumber", label: "Difference", type: "number", render: r => `<span class="${r.differenceNumber >= 0 ? "jma-good-text" : "jma-danger-text"}">${fmt(r.differenceNumber)}</span>` }
    ];

    body.innerHTML = `
      <div class="jma-card jma-category-delivery-card">
        <div class="jma-userbar jma-report-leadbar">
          <div><strong>Category Monthly Delivery Intelligence</strong><span>Monthly delivery, target gap, LD/PD/TD, To Call, and below-target risks</span></div>
          <button id="jma-refresh-category-delivery" type="button">Refresh</button>
        </div>
        <div class="jma-report-scope">Based on <strong>${rows.length}</strong> customer delivery rows and <strong>${summaries.length}</strong> SE/category summary rows detected from the current SMA page.</div>
        <div class="jma-report-grid five">
          ${reportKpi("Customer Rows", rows.length, "rows", "info")}
          ${reportKpi(`Target — ${getPageMonthYearLabel()}`, fmt(totalTarget), "SMS", "purple")}
          ${reportKpi(`Delivery To Date — ${getPageMonthYearLabel()}`, fmt(totalDelivery), "SMS", "good")}
          ${reportKpi("Difference", fmt(totalDiff), "SMS", totalDiff >= 0 ? "good" : "danger")}
          ${reportKpi("BT / Below Target", btCount, "customers", "danger")}
          ${reportKpi("To Call", callCount, "customers", "warn")}
          ${reportKpi("No Delivery", noDelivery, "customers", "danger")}
          ${reportKpi("Displayed Rows", displayedTotals.count, "rows", "neutral")}
          ${reportKpi("Total SMS Delivery", fmt(displayedTotals.totalMessages), "SMS", "good")}
          ${reportKpi("Total OB Balance", fmt(displayedTotals.totalObBalance), "SMS", displayedTotals.totalObBalance < 0 ? "danger" : displayedTotals.totalObBalance === 0 ? "warn" : "info")}
          ${reportKpi("Total PB Balance", fmt(displayedTotals.totalPbBalance), "SMS", displayedTotals.totalPbBalance < 0 ? "danger" : displayedTotals.totalPbBalance === 0 ? "warn" : "info")}
          ${reportKpi("Total Balance", fmt(displayedTotals.totalBalance), "SMS", displayedTotals.totalBalance < 0 ? "danger" : displayedTotals.totalBalance === 0 ? "warn" : "info")}
        </div>
        <div class="jma-definition-strip">
          <span><strong>BT</strong> Delivery below target.</span>
          <span><strong>To Call</strong> 29 days not set a note / CALL flag.</span>
          <span><strong>LD</strong> Local delivery.</span>
          <span><strong>PD</strong> Platform delivery.</span>
        </div>
        <div class="jma-unified-table-toolbar">
          <label>Monthly Delivery Table</label>
          <select class="jma-input" id="jma-category-table-select">
            <option value="customers" ${selectedTable === "customers" ? "selected" : ""}>Customer Delivery Details — Delivery</option>
            <option value="summary" ${selectedTable === "summary" ? "selected" : ""}>SE / Category Summary — Delivery</option>
          </select>
        </div>
        <div class="jma-filter-head jma-category-filter-title"><strong>Delivery Filters</strong><span>Click a filter to update table, Total SMS Delivery and Total Balance.</span></div>
        <div class="jma-filter-row jma-category-filter-row">
          ${[["all","All", rows.length],["att","ATT", rows.filter(r => (r.risks || []).includes("ATT")).length],["bt","BT / Below Target", rows.filter(r => (r.risks || []).includes("BT") || num(r.differenceNumber ?? r.difference) < 0).length],["slowSent","Slow Sent", rows.filter(r => (r.risks || []).includes("Slow Sent")).length],["toCall","To Call", rows.filter(r => (r.risks || []).includes("To Call")).length],["expired","Expired by Date", rows.filter(r => isExpiredByDate(r.expiryDate)).length],["soon","Soon To Be Expired (<=2m)", rows.filter(isCompanyExpiringSoon).length],["noDelivery","No Delivery", rows.filter(r => categoryRowTarget(r) > 0 && categoryRowDelivery(r) === 0).length],["fast","Fast / Above Target", rows.filter(r => categoryRowTarget(r) > 0 && categoryRowDelivery(r) >= categoryRowTarget(r)).length],["free1900","Free Order (1900)", rows.filter(r => isFreeOrder1900(r.expiryDate)).length]].map(([key,label,count]) => `<button type="button" class="jma-filter-chip ${categoryDeliveryState.filter === key ? "active" : ""}" data-category-filter="${key}">${escapeHtml(label)} - ${count}</button>`).join("")}
        </div>
        <div class="jma-filter-head jma-category-filter-title"><strong>Platform Type Filter</strong><span>Commercial, Service, Both, or rows without Platform Type.</span></div>
        ${selectedTable === "customers" ? categoryPlatformTypeFiltersHtml(tableRows) : ""}
        <div class="jma-filter-head jma-category-filter-title"><strong>Balance Filters</strong><span>Zero Balance = balance equals 0. If PB is 0 and no Platform Type is found, PB displays as NA.</span></div>
        ${categoryBalanceFiltersHtml(tableRows)}
        <div class="jma-section-title">${selectedTable === "summary" ? "SE / Category Summary — Delivery" : "Customer Delivery Details — Delivery"}</div>
        ${selectedTable === "summary" ? categoryTableHtml(summaries, summaryColumns, "categorySummary") : categoryTableHtml(rows, customerColumns, "categoryCustomers")}
        <div class="jma-note jma-table-note"><strong>Reasoning note:</strong><br>This screen replicates the monthly category delivery page as an assistant report: it keeps the SE/category summary, customer delivery details, target vs delivery gap, LD/PD/TD breakdown, To Call flags, and below-target delivery risks.</div>
      </div>

      <div class="jma-card jma-chat-card">
        <h3>Category Delivery Chatbot</h3>
        <p class="jma-muted">Ask about the currently displayed category monthly delivery table. Filters and totals are sent with the table data.</p>
        <div class="jma-prompt-row">
          <button class="jma-category-prompt" data-prompt="Summarize this category monthly delivery report.">Summarize report</button>
          <button class="jma-category-prompt" data-prompt="Which customers require follow-up first and why?">Follow-up list</button>
          <button class="jma-category-prompt" data-prompt="Which clients have zero balance?">Zero balance</button>
          <button class="jma-category-prompt" data-prompt="Show the highest balances and top opportunities.">Top opportunities</button>
          <button class="jma-category-prompt" data-prompt="Explain today's KPIs and delivery gaps.">Explain KPIs</button>
        </div>
        <textarea class="jma-chat-input" id="jma-category-chat-input" rows="3" placeholder="Ask about this category monthly delivery report..."></textarea>
        <button class="jma-button" id="jma-run-category-chat" type="button">Ask AI</button>
        <div id="jma-category-chat-output"></div>
      </div>`;

    body.querySelector("#jma-refresh-category-delivery")?.addEventListener("click", drawCategoryMonthlyDeliveryBody);
    body.querySelector("#jma-category-table-select")?.addEventListener("change", e => {
      categoryDeliveryState.table = e.target.value;
      categoryDeliveryState.sortKey = e.target.value === "summary" ? "differenceNumber" : "differenceNumber";
      categoryDeliveryState.direction = "asc";
      drawCategoryMonthlyDeliveryBody();
    });
    body.querySelectorAll("[data-category-filter]").forEach(btn => btn.addEventListener("click", () => { categoryDeliveryState.filter = btn.getAttribute("data-category-filter") || "all"; drawCategoryMonthlyDeliveryBody(); }));
    body.querySelectorAll("[data-category-balance-filter]").forEach(btn => btn.addEventListener("click", () => { categoryDeliveryState.balanceFilter = btn.getAttribute("data-category-balance-filter") || "all"; drawCategoryMonthlyDeliveryBody(); }));
    body.querySelectorAll("[data-category-ob-balance-filter]").forEach(btn => btn.addEventListener("click", () => { categoryDeliveryState.obBalanceFilter = btn.getAttribute("data-category-ob-balance-filter") || "all"; drawCategoryMonthlyDeliveryBody(); }));
    body.querySelectorAll("[data-category-pb-balance-filter]").forEach(btn => btn.addEventListener("click", () => { categoryDeliveryState.pbBalanceFilter = btn.getAttribute("data-category-pb-balance-filter") || "all"; drawCategoryMonthlyDeliveryBody(); }));
    body.querySelectorAll("[data-category-platform-type-filter]").forEach(btn => btn.addEventListener("click", () => { categoryDeliveryState.platformTypeFilter = btn.getAttribute("data-category-platform-type-filter") || "all"; drawCategoryMonthlyDeliveryBody(); }));
    bindReportControls(body);
    bindCategoryLimitControls(body);
    body.querySelectorAll(".jma-category-sort-btn").forEach(btn => btn.addEventListener("click", () => {
      const key = btn.getAttribute("data-sort-key") || "differenceNumber";
      if (categoryDeliveryState.sortKey === key) categoryDeliveryState.direction = categoryDeliveryState.direction === "asc" ? "desc" : "asc";
      else { categoryDeliveryState.sortKey = key; categoryDeliveryState.direction = "desc"; }
      drawCategoryMonthlyDeliveryBody();
    }));
    body.querySelector("#jma-run-category-chat")?.addEventListener("click", () => runCategoryChatbot(body));
    body.querySelectorAll(".jma-category-prompt").forEach(btn => {
      btn.addEventListener("click", () => {
        const input = body.querySelector("#jma-category-chat-input");
        input.value = btn.getAttribute("data-prompt") || "";
        runCategoryChatbot(body);
      });
    });
  }
  function drawUnsupportedBody() {
    const body = document.querySelector(`#${PANEL_ID} .jma-body`);
    if (!body) return;
    body.innerHTML = `
      <div class="jma-card">
        <h3>SMA Assistant+</h3>
        <p class="jma-muted">This SMA URL does not yet have a dedicated assistant screen.</p>
        <div class="jma-kv"><span>Current URL</span><strong>${escapeHtml(sourceUrl())}</strong></div>
        <div class="jma-note"><strong>Configured screens:</strong><br>
          1) salesassignedsmsuserrep.cfm → Executive Reports<br>
          2) noteslistviewallocate.cfm?compid=... → Company Notes Intelligence<br>
          3) CategoryMonthlyDeliveryNewReport.cfm → Category Monthly Delivery Intelligence
        </div>
      </div>`;
  }


  function riskKeyFromVisibleRow(row) {
    const anchors = [...row.querySelectorAll("a")];
    for (const a of anchors) {
      const href = a.getAttribute("href") || "";
      const onclick = a.getAttribute("onclick") || "";
      const text = `${href} ${onclick}`;
      const m = text.match(/(?:cid|compid)=(\d+)|(?:ActiveOrderFrm|menueHistory|menue2)\((\d+)/i);
      const id = m && (m[1] || m[2]);
      if (id) return `id:${id}`;
    }
    const cells = row.children || [];
    const likelyNameCell = cells.length > 2 ? cells[1] : cells[0];
    const nameAnchor = likelyNameCell?.querySelector("a strong") || likelyNameCell?.querySelector("a") || likelyNameCell;
    const name = (nameAnchor?.innerText || "").replace(/Platform Type\s*\(.*?\)/ig, "").replace(/\s+/g, " ").trim().toLowerCase();
    return name ? `name:${name}` : "";
  }

  function sampleVisibleRiskFlags() {
    const cache = window.__JMA_RISK_FLAG_CACHE || {};
    sourceDocument().querySelectorAll("table tbody tr").forEach(row => {
      if (!row.children || row.children.length < 6) return;
      const rowText = row.textContent || "";
      if (!/OB|PB|SMS|B T|BT|ATT|Slow Sent|To Call|CALL|Delivery Todate/i.test(rowText)) return;
      const key = riskKeyFromVisibleRow(row);
      if (!key) return;
      const flags = new Set(cache[key] || []);
      const text = rowText.toUpperCase();
      if (text.includes("ATT")) flags.add("ATT");
      if (text.includes("B T") || /\bBT\b/.test(text)) flags.add("BT");
      if (text.includes("SLOW SENT")) flags.add("Slow Sent");
      if (text.includes("TO CALL") || /\bCALL\b/.test(text)) flags.add("To Call");
      cache[key] = [...flags];
    });
    window.__JMA_RISK_FLAG_CACHE = cache;
  }

  function startRiskSamplingDuringDelay() {
    window.__JMA_RISK_FLAG_CACHE = {};
    if (riskSamplingTimer) window.clearInterval(riskSamplingTimer);
    sampleVisibleRiskFlags();
    riskSamplingTimer = window.setInterval(sampleVisibleRiskFlags, 200);
    window.setTimeout(() => {
      sampleVisibleRiskFlags();
      if (riskSamplingTimer) window.clearInterval(riskSamplingTimer);
      riskSamplingTimer = null;
    }, REPORT_SCREEN_CAPTURE_DELAY_MS);
  }

  function drawBody() {
    const screen = getCurrentSmaScreen();
    if (screen === "sales-report") return drawSalesReportBody();
    if (screen === "company-notes") return drawCompanyNotesBody();
    if (screen === "category-monthly-delivery") return drawCategoryMonthlyDeliveryBody();
    return drawUnsupportedBody();
  }


  function renderShell() {
    const existing = document.getElementById(PANEL_ID);
    if (!isSupportedSmaScreen()) {
      if (existing) existing.remove();
      document.documentElement.classList.remove("jma-page-shifted");
      document.body.classList.remove("jma-page-shifted");
      notifyFrameState("unsupported");
      return;
    }
    notifyFrameState("closed");
    if (existing) existing.remove();

    const logoUrl = window.JORMALL_SMA_OVERLAY_CONFIG?.logoUrl || "";

    const root = el("div", "jma-root");
    root.id = PANEL_ID;
    root.innerHTML = `
      <button class="jma-toggle" type="button" aria-label="Open SMA Assistant+">
        <span class="jma-toggle-icon">✦</span>
        <span class="jma-toggle-text">SMA TEST 23</span>
      </button>
      <aside class="jma-panel jma-hidden" role="complementary" aria-label="SMA Assistant+">
        <button class="jma-resize-handle" type="button" title="Drag to resize SMA Assistant width and height" aria-label="Resize SMA Assistant">↙</button>
        <div class="jma-header">
          <div class="jma-brand">
            ${logoUrl ? `<img class="jma-logo" src="${logoUrl}" alt="JorMall">` : ""}
            <div>
              <strong>SMA Assistant+ — TEST 20260823</strong>
              <span>Independent test environment · production remains unchanged</span>
            </div>
          </div>
          <button class="jma-close" type="button" aria-label="Close">×</button>
        </div>
        <div class="jma-body"></div>
      </aside>`;

    document.body.appendChild(root);

    const panel = root.querySelector(".jma-panel");
    const toggle = root.querySelector(".jma-toggle");
    const close = root.querySelector(".jma-close");
    const resizeHandle = root.querySelector(".jma-resize-handle");

    const savedSize = (() => {
      try { return JSON.parse(localStorage.getItem("jmaAssistantPanelSize") || "{}"); } catch (_) { return {}; }
    })();
    if (savedSize.width) panel.style.setProperty("--jma-panel-width", savedSize.width);
    if (savedSize.height) panel.style.setProperty("--jma-panel-height", savedSize.height);

    const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
    resizeHandle?.addEventListener("mousedown", event => {
      event.preventDefault();
      const startX = event.clientX;
      const startY = event.clientY;
      const rect = panel.getBoundingClientRect();
      const startWidth = rect.width;
      const startHeight = rect.height;
      document.body.classList.add("jma-resizing");
      const move = moveEvent => {
        const nextWidth = clamp(startWidth + (startX - moveEvent.clientX), 360, Math.floor(window.innerWidth * 0.98));
        const nextHeight = clamp(startHeight + (moveEvent.clientY - startY), 420, Math.floor(window.innerHeight - 20));
        panel.style.setProperty("--jma-panel-width", `${nextWidth}px`);
        panel.style.setProperty("--jma-panel-height", `${nextHeight}px`);
      };
      const up = () => {
        document.removeEventListener("mousemove", move);
        document.removeEventListener("mouseup", up);
        document.body.classList.remove("jma-resizing");
        localStorage.setItem("jmaAssistantPanelSize", JSON.stringify({
          width: panel.style.getPropertyValue("--jma-panel-width"),
          height: panel.style.getPropertyValue("--jma-panel-height")
        }));
      };
      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", up);
    });

    const openPanel = () => {
      notifyFrameState("open");
      panel.classList.remove("jma-hidden");
      toggle.classList.add("jma-hidden");
      document.documentElement.classList.add("jma-page-shifted");
      document.body.classList.add("jma-page-shifted");
      const body = root.querySelector(".jma-body");
      if (["sales-report", "category-monthly-delivery"].includes(getCurrentSmaScreen())) {
        body.innerHTML = `<div class="jma-card"><h3>Preparing report screen...</h3><p class="jma-muted">Watching the SMA report for 2 seconds and locking the maximum observed ATT, BT, Slow Sent, and To Call flags so the counts stay stable.</p></div>`;
        startRiskSamplingDuringDelay();
        window.setTimeout(drawBody, REPORT_SCREEN_CAPTURE_DELAY_MS);
      } else {
        drawBody();
      }
    };

    const closePanel = () => {
      notifyFrameState("closed");
      panel.classList.add("jma-hidden");
      toggle.classList.remove("jma-hidden");
      document.documentElement.classList.remove("jma-page-shifted");
      document.body.classList.remove("jma-page-shifted");
    };

    toggle.addEventListener("click", openPanel);
    close.addEventListener("click", closePanel);
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && !panel.classList.contains("jma-hidden")) closePanel();
    });

    // Do not auto-open the assistant. Keep only the Reports button visible until clicked.
  }


  function syncAssistantForCurrentScreen() {
    const existing = document.getElementById(PANEL_ID);
    if (isSupportedSmaScreen()) {
      if (!existing) renderShell();
    } else if (existing) {
      existing.remove();
      document.documentElement.classList.remove("jma-page-shifted");
      document.body.classList.remove("jma-page-shifted");
    }
  }

  syncAssistantForCurrentScreen();
  let lastAssistantHref = sourceUrl();
  window.JorMallSMAHostedRefresh = () => {
    const nextHref = sourceUrl();
    const existing = document.getElementById(PANEL_ID);
    const wasOpen = Boolean(existing?.querySelector(".jma-panel:not(.jma-hidden)"));
    if (nextHref !== lastAssistantHref) {
      lastAssistantHref = nextHref;
      syncAssistantForCurrentScreen();
      return;
    }
    if (!existing) {
      syncAssistantForCurrentScreen();
      return;
    }
    if (wasOpen) drawBody();
  };
})()
