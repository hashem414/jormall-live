const chatbotConfig = window.CHATBOT_CONFIG || {};
const footerCompanyName =
    chatbotConfig.displayCompanyName || chatbotConfig.companyName || "JorMall";
function configuredFooter(language) {
    const configured =
        language === "ar"
            ? chatbotConfig.footerTextAr
            : chatbotConfig.footerTextEn;

    return (
        configured ||
        `${chatbotConfig.assistantName || "JorMall Assistant"} \u2013 ${footerCompanyName} \u2022 \u00a9 2026. All rights reserved.`
    );
}

const translations = {
    en: {
        approvedOnly: "",
        heroTitle: "JorMall Assistant",
        heroSubtitle:
            "Ask questions about JorMall services, approved policies, pricing information, and more.",
        chatEyebrow: "",
        chatHeading: "How can we help?",
        sourceOnly: "",
        tryAsking: "Try asking",
        send: "Send \u2192",
        newChat: "New chat",
        footerNote: configuredFooter("en"),
        placeholder: "Ask a question about JorMall...",
        welcome:
            "Welcome to JorMall Assistant. Ask me about JorMall.",
        searching: "Checking available information...",
        serviceError:
            "The JorMall assistant is temporarily unavailable. Please try again later.",
        leadTitle: "Start your conversation",
        leadSubtitle: "Please enter your name and mobile number to continue to the chatbot.",
        leadNameLabel: "Name",
        leadPhoneLabel: "Mobile Number",
        leadNamePlaceholder: "Ahmed Sami",
        leadPhonePlaceholder: "07XXXXXXXX",
        leadContinue: "Continue",
        leadPrivacy:
            "Your contact details will be used to follow up regarding this service.",
        leadCookieConsent:
            "I accept the use of necessary cookies for this chatbot.",
        leadPrivacyConsent:
            "I agree to the applicable TRC requirements and to the processing of my personal data in accordance with Jordan’s Personal Data Protection Law (PDPL).",
        leadNameError: "Please enter your first and last name.",
        leadPhoneError:
            "Please enter a valid 10-digit Jordanian mobile number starting with 07.",
        leadCookieConsentError:
            "You must accept the necessary cookies to continue.",
        leadPrivacyConsentError:
            "You must agree to the applicable privacy and data-processing requirements to continue.",
        leadSubmitError: "We could not save your details. Please try again.",
        leadChecking: "Checking your details...",
        leadSaving: "Saving your details...",
        requestCallAction: "Request a sales callback",
        callbackTitle: "Sales callback request",
        callbackPrompt:
            "Please briefly tell our sales team how they can help you.",
        callbackMessageLabel: "Message",
        callbackMessagePlaceholder: "Tell us what you need help with...",
        callbackConfirm: "Submit callback request",
        callbackCancel: "Cancel",
        callbackSubmitting: "Sending request...",
        callbackSuccess:
            "Thank you. Your callback request has been sent to our sales team. They will contact you using the number you provided.",
        callbackError: "We could not save your call request. Please try again.",
        callbackMessageTooLong: "Please keep the message under 1,000 characters.",
        contactCardTitle: "Contact JorMall",
        contactEmail: "Email",
        contactCustomerService: "Customer Service",
        contactTelephone: "Telephone",
        contactWebsite: "Website",
        contactAddress: "Address",
        suggestions: [
            "What is Smart Reach SMS?",
            "Does JorMall provide delivery reports?",
            "What are the free SMS bonus percentages?",
            "What are the contract approval requirements?"
        ]
    },

    ar: {
        approvedOnly: "",
        heroTitle: "مساعد JorMall",
        heroSubtitle:
            "اسأل عن خدمات JorMall والسياسات المعتمدة ومعلومات الأسعار وغيرها.",
        chatEyebrow: "",
        chatHeading: "كيف يمكننا مساعدتك؟",
        sourceOnly: "",
        tryAsking: "جرّب أن تسأل",
        send: "\u0625\u0631\u0633\u0627\u0644 \u2192",
        newChat: "محادثة جديدة",
        footerNote: configuredFooter("ar"),
        placeholder: "اكتب سؤالك عن JorMall...",
        welcome:
            "مرحبًا بك في مساعد JorMall. اسألني عن JorMall.",
        searching: "جارٍ البحث في المعلومات المتاحة...",
        serviceError:
            "مساعد JorMall غير متاح مؤقتًا. يرجى المحاولة مرة أخرى لاحقًا.",
        leadTitle: "ابدأ المحادثة",
        leadSubtitle: "يرجى إدخال اسمك ورقم هاتفك للمتابعة إلى الشات بوت.",
        leadNameLabel: "الاسم",
        leadPhoneLabel: "رقم الهاتف",
        leadNamePlaceholder: "أحمد سامي",
        leadPhonePlaceholder: "07XXXXXXXX",
        leadContinue: "متابعة",
        leadPrivacy:
            "سيتم استخدام بيانات التواصل الخاصة بك للمتابعة بشأن هذه الخدمة.",
        leadCookieConsent:
            "أوافق على استخدام ملفات تعريف الارتباط الضرورية لتشغيل هذا الشات بوت.",
        leadPrivacyConsent:
            "أوافق على المتطلبات المعمول بها لدى هيئة تنظيم قطاع الاتصالات، وعلى معالجة بياناتي الشخصية وفقًا لقانون حماية البيانات الشخصية الأردني.",
        leadNameError: "يرجى إدخال الاسم الأول واسم العائلة.",
        leadPhoneError:
            "يرجى إدخال رقم هاتف أردني صحيح مكوّن من 10 أرقام ويبدأ بـ 07.",
        leadCookieConsentError:
            "يجب الموافقة على استخدام ملفات تعريف الارتباط الضرورية للمتابعة.",
        leadPrivacyConsentError:
            "يجب الموافقة على متطلبات الخصوصية ومعالجة البيانات للمتابعة.",
        leadSubmitError: "تعذر حفظ بياناتك. يرجى المحاولة مرة أخرى.",
        leadChecking: "جارٍ التحقق من بياناتك...",
        leadSaving: "جارٍ حفظ بياناتك...",
        requestCallAction: "طلب اتصال من فريق المبيعات",
        callbackTitle: "طلب اتصال من فريق المبيعات",
        callbackPrompt:
            "يرجى كتابة رسالة قصيرة توضح كيف يمكن لفريق المبيعات مساعدتك.",
        callbackMessageLabel: "الرسالة",
        callbackMessagePlaceholder: "اكتب رسالتك هنا...",
        callbackConfirm: "إرسال طلب الاتصال",
        callbackCancel: "إلغاء",
        callbackSubmitting: "جارٍ إرسال الطلب...",
        callbackSuccess:
            "شكراً لك. تم إرسال طلب الاتصال إلى فريق المبيعات، وسيتم التواصل معك على رقم الهاتف الذي أدخلته.",
        callbackError: "تعذر حفظ طلب الاتصال. يرجى المحاولة مرة أخرى.",
        callbackMessageTooLong: "يرجى ألا تتجاوز الرسالة 1,000 حرف.",
        contactCardTitle: "تواصل مع JorMall",
        contactEmail: "البريد الإلكتروني",
        contactCustomerService: "خدمة العملاء",
        contactTelephone: "الهاتف",
        contactWebsite: "الموقع الإلكتروني",
        contactAddress: "العنوان",
        suggestions: [
            "ما هي خدمات الرسائل القصيرة التي تقدمها JorMall؟",
            "هل توفر JorMall تقارير تسليم الرسائل؟",
            "ما هي نسب الرسائل المجانية حسب مدة العقد؟",
            "ما هي متطلبات اعتماد العقود مع الزبائن؟"
        ]
    }
};

function localizedSuggestedQuestions(language) {
    const configuredItems = Array.isArray(chatbotConfig.starterQuestionItems)
        ? chatbotConfig.starterQuestionItems
        : [];
    const itemSuggestions = configuredItems
        .map((item) => {
            const label =
                language === "ar"
                    ? item.label_ar
                    : item.label_en;

            if (!label) {
                return null;
            }

            return {
                id: item.id || "",
                type: item.type || "question",
                label
            };
        })
        .filter(Boolean);

    if (itemSuggestions.length) {
        return itemSuggestions;
    }

    const configuredQuestions = chatbotConfig.suggestedQuestions;

    if (Array.isArray(configuredQuestions)) {
        return (language === "en" ? configuredQuestions : [])
            .filter(Boolean)
            .map((label) => ({ id: "", type: "question", label }));
    }

    if (configuredQuestions && typeof configuredQuestions === "object") {
        const languageQuestions = Array.isArray(configuredQuestions[language])
            ? configuredQuestions[language].filter(Boolean)
            : [];

        if (languageQuestions.length) {
            return languageQuestions.map((label) => ({
                id: "",
                type: "question",
                label
            }));
        }

        const englishQuestions = Array.isArray(configuredQuestions.en)
            ? configuredQuestions.en.filter(Boolean)
            : [];

        return language === "en"
            ? englishQuestions.map((label) => ({
                  id: "",
                  type: "question",
                  label
              }))
            : [];
    }

    return [];
}

if (chatbotConfig.companyName) {
    const assistantName =
        chatbotConfig.assistantName ||
        `${chatbotConfig.companyName} Assistant`;

    translations.en.approvedOnly = "";
    translations.en.heroTitle = assistantName;
    translations.en.heroSubtitle =
        `Ask about ${chatbotConfig.companyName} services, policies, and support information.`;
    translations.en.sourceOnly = "";
    translations.en.footerNote = configuredFooter("en");
    translations.en.placeholder = `Ask a question about ${chatbotConfig.companyName}...`;
    translations.en.welcome =
        chatbotConfig.openingMessageEn ||
        (chatbotConfig.chatbotType === "campaign"
            ? `Welcome to ${assistantName}. Ask me about ${chatbotConfig.campaignName || chatbotConfig.companyName}.`
            : `Welcome to ${assistantName}. Ask me about ${chatbotConfig.companyName}.`);
    translations.en.searching =
        "Checking available information...";
    translations.en.serviceError =
        `The ${assistantName} is temporarily unavailable. Please try again later.`;
    translations.en.suggestions = localizedSuggestedQuestions("en");

    translations.ar.approvedOnly = "";
    translations.ar.heroTitle = `مساعد ${chatbotConfig.companyName}`;
    translations.ar.heroSubtitle =
        `اسأل عن ${chatbotConfig.companyName} وخدماتها والمعلومات المتاحة عنها.`;
    translations.ar.sourceOnly = "";
    translations.ar.footerNote = configuredFooter("ar");
    translations.ar.placeholder = `اكتب سؤالك عن ${chatbotConfig.companyName}...`;
    translations.ar.welcome =
        `مرحبًا بك في مساعد ${chatbotConfig.companyName}. اسألني عن ${chatbotConfig.companyName}.`;
    translations.ar.searching = "جارٍ البحث في المعلومات المتاحة...";
    translations.ar.serviceError =
        `مساعد ${chatbotConfig.companyName} غير متاح مؤقتًا. يرجى المحاولة لاحقًا.`;
    translations.ar.heroTitle = assistantName;
    translations.ar.suggestions = localizedSuggestedQuestions("ar");
    if (chatbotConfig.chatbotType === "campaign") {
        translations.ar.welcome =
            chatbotConfig.openingMessageAr ||
            `مرحبًا بك في ${assistantName}. اسألني عن ${chatbotConfig.campaignName || chatbotConfig.companyName}.`;
    }
}


const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatMessages = document.getElementById("chat-messages");
const sendButton = document.getElementById("send-button");
const newChatButton = document.getElementById("new-chat-button");
const suggestionList = document.getElementById("suggestion-list");
const leadOverlay = document.getElementById("prechat-lead-overlay");
const leadForm = document.getElementById("prechat-lead-form");
const leadNameInput = document.getElementById("prechat-lead-name");
const leadPhoneInput = document.getElementById("prechat-lead-phone");
const leadCookieConsentInput = document.getElementById("prechat-cookie-consent");
const leadPrivacyConsentInput = document.getElementById("prechat-privacy-consent");
const leadSubmitButton = document.getElementById("prechat-lead-submit");
const leadNameError = document.getElementById("prechat-lead-name-error");
const leadPhoneError = document.getElementById("prechat-lead-phone-error");
const leadCookieConsentError = document.getElementById("prechat-cookie-consent-error");
const leadPrivacyConsentError = document.getElementById("prechat-privacy-consent-error");
const leadStatus = document.getElementById("prechat-lead-status");
let leadNameTouched = false;
let leadPhoneTouched = false;
let leadCookieConsentTouched = false;
let leadPrivacyConsentTouched = false;
let leadSubmitAttempted = false;

let welcomeMessage = document.getElementById("welcome-message");

const welcomeArticle = welcomeMessage
    ? welcomeMessage.closest(".message")
    : null;

const welcomeMessageTemplate = welcomeArticle
    ? welcomeArticle.cloneNode(true)
    : null;


/*
    Browser-session memory.

    The frontend no longer decides whether a message is:
    - memory request
    - document request
    - clarification request

    That decision now belongs to the backend Conversation Brain.

    The frontend only:
    1. stores the visible conversation,
    2. sends recent conversation JSON to the backend,
    3. displays the streamed response.
*/
const MEMORY_STORAGE_KEY =
    `client_chat_session_history_${chatbotConfig.clientSlug || "jormall"}_v2`;
const SESSION_ID_STORAGE_KEY =
    `client_chat_session_id_${chatbotConfig.clientSlug || "jormall"}_v1`;
const LEAD_SESSION_ID_STORAGE_KEY =
    `client_chat_lead_session_id_${chatbotConfig.clientSlug || "jormall"}_v1`;
const SALES_CALLBACK_ACTION_MARKER = "[[sales_callback_action]]";
const SALES_CALLBACK_ACTION_PATTERN = /\[\[sales_callback_action(?::([a-z]+))?\]\]/g;
const SALES_CALLBACK_ACTION_TEXT = {
    en: "Request a sales callback",
    ar: "طلب اتصال من فريق المبيعات"
};
const EVIDENCE_STORAGE_KEY =
    `evidence_history_${chatbotConfig.clientSlug || "jormall"}`;
const LEGACY_EVIDENCE_STORAGE_KEY =
    `client_chat_evidence_history_${chatbotConfig.clientSlug || "jormall"}_v1`;
const MAX_MEMORY_TURNS = 40;
const MAX_BACKEND_HISTORY_TURNS = 16;
const MAX_EVIDENCE_BUNDLES = 8;
const MAX_MEMORY_CHARACTERS = 1600;
const MAX_BACKEND_HISTORY_CHARACTERS = 800;

const MEDIA_MARKER_PATTERN =
    /\[\[(image|video):([^|\]\r\n]+)\|([^\]\r\n]*)\]\]/gi;

let currentLanguage = "en";
let isWaitingForResponse = false;
let sessionId = loadSessionId();
let leadSessionId = loadLeadSessionId();
let isLeadGateOpen = Boolean(chatbotConfig.leadCaptureEnabled);
let isLeadSubmitting = false;
let starterActionInFlight = false;
let activeStarterButton = null;
let hasPendingSalesCallback = false;
let conversationMemory = loadConversationMemory();
let evidenceMemory = loadEvidenceMemory();


function containsArabic(text) {
    return /[\u0600-\u06FF]/.test(text);
}


const PHONE_NUMBER_PATTERN = /(?:\+962(?:[\s-]?\d){8,9}|07(?:[\s-]?\d){8})/g;


function telHref(value) {
    const compact = String(value || "").replace(/[^\d+]/g, "");
    return compact ? `tel:${compact}` : "";
}


function appendPhoneIsolatedText(container, text, { linkPhones = false } = {}) {
    container.textContent = "";

    const value = String(text || "");
    let cursor = 0;

    for (const match of value.matchAll(PHONE_NUMBER_PATTERN)) {
        const phone = match[0];
        const index = match.index || 0;

        if (index > cursor) {
            container.appendChild(document.createTextNode(value.slice(cursor, index)));
        }

        const element = linkPhones ? document.createElement("a") : document.createElement("span");
        element.className = "phone-number";
        element.dir = "ltr";
        element.textContent = phone;
        if (linkPhones) {
            element.href = telHref(phone);
        }
        container.appendChild(element);
        cursor = index + phone.length;
    }

    if (cursor < value.length) {
        container.appendChild(document.createTextNode(value.slice(cursor)));
    }
}


function normalizeWhitespace(text) {
    return String(text)
        .replace(/\s+/g, " ")
        .trim();
}


function cleanMediaUrl(url) {
    return String(url || "")
        .trim()
        .replace(/[.,;:)\]}]+$/g, "");
}


function appBasePath() {
    return String(chatbotConfig.appBasePath || "").replace(/\/+$/, "");
}


function stripAppBasePath(url) {
    const cleanedUrl = cleanMediaUrl(url);
    const basePath = appBasePath();
    if (basePath && cleanedUrl.startsWith(`${basePath}/`)) {
        return cleanedUrl.slice(basePath.length) || "/";
    }
    return cleanedUrl;
}


function cleanMediaLabel(label) {
    return normalizeWhitespace(
        label || `${chatbotConfig.companyName || "Client"} source evidence`
    );
}


function isAllowedImageUrl(url) {
    const normalizedUrl = stripAppBasePath(url);
    return (
        /^\/api\/media\/[a-z0-9-]+\/[0-9a-f-]+\/[0-9a-f-]+\/(?:approved|thumbnail)$/i.test(normalizedUrl) ||
        /^\/static\/scraped_sources\/(?:[a-z0-9-]+\/)?(?:images|screenshots|document_images)\/.+\.(png|jpg|jpeg|webp|gif)$/i.test(normalizedUrl) ||
        /^https?:\/\/.+\.(png|jpg|jpeg|webp|gif)(?:\?.*)?$/i.test(normalizedUrl)
    );
}


function isAllowedVideoUrl(url) {
    const normalizedUrl = stripAppBasePath(url);
    return (
        /^https?:\/\/.+\.(mp4|webm|mov|m4v)(\?.*)?$/i.test(normalizedUrl) ||
        /^\/static\/scraped_sources\/(?:[a-z0-9-]+\/)?videos\/.+\.(mp4|webm|mov|m4v)$/i.test(normalizedUrl)
    );
}


function normalizeMediaItem(item) {
    if (!item || typeof item !== "object") {
        return null;
    }

    const type = String(item.type || "").toLowerCase();
    const url = cleanMediaUrl(item.url);
    const label = cleanMediaLabel(item.label);
    const fallbackUrl = cleanMediaUrl(item.fallback_url);
    const source = String(item.source || "approved_jormall_evidence");

    if (!["image", "video"].includes(type) || !url) {
        return null;
    }

    if (type === "image" && !isAllowedImageUrl(url)) {
        return null;
    }

    if (type === "video" && !isAllowedVideoUrl(url)) {
        return null;
    }

    return {
        type,
        id: normalizeWhitespace(item.id || item.image_id || ""),
        url,
        label,
        fallback_url:
            type === "image" && fallbackUrl && isAllowedImageUrl(fallbackUrl)
                ? fallbackUrl
                : "",
        thumbnail_url: cleanMediaUrl(item.thumbnail_url || ""),
        title: normalizeWhitespace(item.title || ""),
        caption: normalizeWhitespace(item.caption || ""),
        description: normalizeWhitespace(item.description || ""),
        alt_text: normalizeWhitespace(item.alt_text || item.altText || label),
        title_en: normalizeWhitespace(item.title_en || ""),
        title_ar: normalizeWhitespace(item.title_ar || ""),
        product_url: cleanMediaUrl(item.product_url),
        current_price: normalizeWhitespace(item.current_price || ""),
        old_price: normalizeWhitespace(item.old_price || ""),
        source
    };
}


function mergeMediaItems(...mediaGroups) {
    const seen = new Map();
    const merged = [];

    for (const group of mediaGroups) {
        if (!Array.isArray(group)) {
            continue;
        }

        for (const rawItem of group) {
            const item = normalizeMediaItem(rawItem);

            if (!item) {
                continue;
            }

            const aliases = [
                item.id ? `${item.type}:id:${item.id}` : "",
                item.url ? `${item.type}:url:${item.url}` : "",
                item.fallback_url ? `${item.type}:fallback:${item.fallback_url}` : ""
            ].filter(Boolean);
            const existingIndex = aliases
                .map((alias) => seen.get(alias))
                .find((index) => index !== undefined);

            if (existingIndex !== undefined) {
                const existing = merged[existingIndex];
                for (const [field, value] of Object.entries(item)) {
                    if (!existing[field] && value) {
                        existing[field] = value;
                    }
                }
                for (const alias of aliases) {
                    seen.set(alias, existingIndex);
                }
                continue;
            }

            for (const alias of aliases) {
                seen.set(alias, merged.length);
            }
            merged.push(item);
        }
    }

    return merged;
}


function extractMediaMarkers(text) {
    const mediaItems = [];

    const cleanedText = String(text || "").replace(
        MEDIA_MARKER_PATTERN,
        (fullMatch, type, url, label) => {
            const mediaItem = normalizeMediaItem({
                type,
                url,
                label
            });

            if (mediaItem) {
                mediaItems.push(mediaItem);
            }

            return "";
        }
    );

    return {
        text: cleanedText
            .replace(/\n{3,}/g, "\n\n")
            .trim(),
        media: mediaItems
    };
}


function removeMediaMarkers(text) {
    return extractMediaMarkers(text).text;
}


function removeClientSourceSection(text) {
    return String(text)
        .replace(
            /\s*(?:Sources used|المصادر المستخدمة)\s*(?:\r?\n[\s\S]*)?$/i,
            ""
        )
        .trim();
}


function removeSuggestedFollowUpSection(text) {
    return String(text)
        .replace(
            /\s*(?:Suggested follow-up questions:|أسئلة متابعة مقترحة:)\s*[\s\S]*$/i,
            ""
        )
        .trim();
}


function removeSalesCallbackActionMarker(text) {
    return String(text).replace(/\[\[sales_callback_action(?::([a-z]+))?\]\]/g, "").trim();
}


function cleanVisibleAssistantText(text) {
    return removeSuggestedFollowUpSection(
        removeClientSourceSection(
            removeSalesCallbackActionMarker(removeMediaMarkers(text))
        )
    ).trim();
}


function parseAssistantContent(text, extraMedia = []) {
    const extracted = extractMediaMarkers(text);

    let hasSalesCallbackAction = false;
    let salesCallbackLanguage = null;
    const match = /\[\[sales_callback_action(?::([a-z]+))?\]\]/.exec(text);
    if (match) {
        hasSalesCallbackAction = true;
        if (match[1]) {
            salesCallbackLanguage = match[1];
        }
    }

    return {
        text: cleanVisibleAssistantText(extracted.text),
        media: mergeMediaItems(extracted.media, extraMedia),
        hasSalesCallbackAction,
        salesCallbackLanguage,
        salesCallbackAction: hasSalesCallbackAction
            ? normalizeSalesCallbackAction({
                  type: "request_sales_callback",
                  language: salesCallbackLanguage
              })
            : null
    };
}


function normalizeSalesCallbackAction(action = {}) {
    if (action?.type !== "request_sales_callback") {
        return null;
    }

    const language = action.language === "ar" ? "ar" : action.language === "en" ? "en" : null;
    const fallbackLanguage = language || currentLanguage;
    const label = String(action.label || "").trim() ||
        translations[fallbackLanguage]?.requestCallAction ||
        translations[currentLanguage].requestCallAction;

    return {
        type: "request_sales_callback",
        language: fallbackLanguage,
        label
    };
}


function cleanMemoryContent(content) {
    return cleanVisibleAssistantText(content)
        .slice(0, MAX_MEMORY_CHARACTERS);
}


function cleanBackendHistoryContent(content) {
    return cleanVisibleAssistantText(content)
        .slice(0, MAX_BACKEND_HISTORY_CHARACTERS);
}


function meaningfullyDifferentText(a, b) {
    const left = normalizeWhitespace(a).toLowerCase();
    const right = normalizeWhitespace(b).toLowerCase();

    return Boolean(left && right && left !== right);
}


function loadConversationMemory() {
    try {
        const storedHistory = sessionStorage.getItem(
            MEMORY_STORAGE_KEY
        );

        if (!storedHistory) {
            return [];
        }

        const parsedHistory = JSON.parse(storedHistory);

        if (!Array.isArray(parsedHistory)) {
            return [];
        }

        return parsedHistory
            .map((turn) => {
                if (
                    !turn ||
                    !["user", "assistant"].includes(turn.role)
                ) {
                    return null;
                }

                const content = cleanMemoryContent(turn.content);

                if (!content) {
                    return null;
                }

                return {
                    role: turn.role,
                    content
                };
            })
            .filter(Boolean)
            .slice(-MAX_MEMORY_TURNS);
    } catch {
        return [];
    }
}


function createSessionId() {
    if (window.crypto?.randomUUID) {
        return window.crypto.randomUUID();
    }

    return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}


function loadSessionId() {
    const configuredSessionId = String(chatbotConfig.sessionId || "").trim();

    if (configuredSessionId) {
        try {
            localStorage.setItem(SESSION_ID_STORAGE_KEY, configuredSessionId);
        } catch {
            /*
                Embedded third-party contexts can block storage. The configured
                session id is still sent to the backend for this request flow.
            */
        }

        return configuredSessionId;
    }

    try {
        const storedSessionId = localStorage.getItem(SESSION_ID_STORAGE_KEY);

        if (storedSessionId) {
            return storedSessionId;
        }

        const nextSessionId = createSessionId();
        localStorage.setItem(SESSION_ID_STORAGE_KEY, nextSessionId);
        return nextSessionId;
    } catch {
        return createSessionId();
    }
}


function loadLeadSessionId() {
    if (!chatbotConfig.leadCaptureEnabled) {
        return sessionId;
    }

    try {
        const storedLeadSessionId = localStorage.getItem(
            LEAD_SESSION_ID_STORAGE_KEY
        );

        if (storedLeadSessionId) {
            return storedLeadSessionId;
        }

        localStorage.setItem(LEAD_SESSION_ID_STORAGE_KEY, sessionId);
        return sessionId;
    } catch {
        return sessionId;
    }
}


function notifyEmbedParent(type) {
    if (!chatbotConfig.embedMode || !chatbotConfig.embedParentOrigin) {
        return;
    }

    try {
        window.parent.postMessage(
            {
                source: "jormall-chatbot",
                type,
                clientSlug: chatbotConfig.clientSlug || "jormall"
            },
            chatbotConfig.embedParentOrigin
        );
    } catch {
        /*
            Parent messaging is optional; chat remains usable without it.
        */
    }
}


function normalizeEvidenceBundle(bundle) {
    if (!bundle || typeof bundle !== "object") {
        return null;
    }

    const clientSlug = chatbotConfig.clientSlug || "jormall";

    if (bundle.client_slug && bundle.client_slug !== clientSlug) {
        return null;
    }

    const items = Array.isArray(bundle.items)
        ? bundle.items
              .filter((item) => item && typeof item === "object")
              .slice(0, 8)
              .map((item) => ({
                  client_slug: String(item.client_slug || clientSlug),
                  document_id: String(item.document_id || ""),
                  chunk_id: String(item.chunk_id || ""),
                  document_title: String(item.document_title || ""),
                  original_filename: String(item.original_filename || ""),
                  source_type: String(item.source_type || ""),
                  document_type: String(item.document_type || ""),
                  source_reference: String(item.source_reference || ""),
                  source_url: String(item.source_url || ""),
                  page_url: String(item.page_url || ""),
                  local_static_url: String(item.local_static_url || ""),
                  screenshot_url: String(item.screenshot_url || ""),
                  video_url: String(item.video_url || ""),
                  section_title: String(item.section_title || ""),
                  content_preview: String(item.content_preview || "").slice(0, 700)
              }))
              .filter((item) => item.chunk_id || item.document_title || item.original_filename)
        : [];

    if (!items.length) {
        return null;
    }

    return {
        version: 1,
        client_slug: clientSlug,
        question: String(bundle.question || "").slice(0, 500),
        answer_preview: String(bundle.answer_preview || "").slice(0, 900),
        items
    };
}


function loadEvidenceMemory() {
    try {
        const storedEvidence =
            sessionStorage.getItem(EVIDENCE_STORAGE_KEY) ||
            sessionStorage.getItem(LEGACY_EVIDENCE_STORAGE_KEY);

        if (!storedEvidence) {
            return [];
        }

        const parsedEvidence = JSON.parse(storedEvidence);

        if (!Array.isArray(parsedEvidence)) {
            return [];
        }

        return parsedEvidence
            .map(normalizeEvidenceBundle)
            .filter(Boolean)
            .slice(-MAX_EVIDENCE_BUNDLES);
    } catch {
        return [];
    }
}


function saveConversationMemory() {
    try {
        sessionStorage.setItem(
            MEMORY_STORAGE_KEY,
            JSON.stringify(conversationMemory)
        );
    } catch {
        /*
            Chat still works if browser storage is unavailable.
        */
    }
}


function saveEvidenceMemory() {
    try {
        sessionStorage.setItem(
            EVIDENCE_STORAGE_KEY,
            JSON.stringify(evidenceMemory)
        );
    } catch {
        /*
            Evidence follow-ups can still fall back to backend retrieval.
        */
    }
}


function rememberTurn(role, content) {
    const cleanedContent = cleanMemoryContent(content);

    if (!cleanedContent) {
        return;
    }

    conversationMemory.push({
        role,
        content: cleanedContent
    });

    conversationMemory = conversationMemory.slice(
        -MAX_MEMORY_TURNS
    );

    saveConversationMemory();
}


function rememberEvidenceBundle(bundle) {
    const normalizedBundle = normalizeEvidenceBundle(bundle);

    if (!normalizedBundle) {
        return;
    }

    evidenceMemory.push(normalizedBundle);
    evidenceMemory = evidenceMemory.slice(-MAX_EVIDENCE_BUNDLES);
    saveEvidenceMemory();
}


function getHistoryForRequest() {
    return conversationMemory
        .slice(-MAX_BACKEND_HISTORY_TURNS)
        .map((turn) => ({
            role: turn.role,
            content: cleanBackendHistoryContent(turn.content)
        }))
        .filter((turn) => turn.content);
}


function getEvidenceHistoryForRequest() {
    return evidenceMemory
        .map(normalizeEvidenceBundle)
        .filter(Boolean)
        .slice(-MAX_EVIDENCE_BUNDLES);
}


function scrollToLatestMessage() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}


function resizeInput() {
    chatInput.style.height = "auto";

    chatInput.style.height = `${Math.min(
        chatInput.scrollHeight,
        135
    )}px`;
}


function setLoadingState(isLoading) {
    isWaitingForResponse = isLoading;

    sendButton.disabled = isLoading || isLeadGateOpen;
    chatInput.disabled = isLoading || isLeadGateOpen;

    if (newChatButton) {
        newChatButton.disabled = isLoading || isLeadGateOpen;
    }

    if (!isLoading && !isLeadGateOpen) {
        chatInput.focus();
    }

    updateSuggestionButtonDisabledStates();
}


function setLeadGateOpen(isOpen) {
    isLeadGateOpen = Boolean(isOpen);

    if (leadOverlay) {
        leadOverlay.hidden = !isLeadGateOpen;
    }

    document.documentElement.classList.toggle(
        "prechat-lead-locked",
        isLeadGateOpen
    );
    sendButton.disabled = isLeadGateOpen || isWaitingForResponse;
    chatInput.disabled = isLeadGateOpen || isWaitingForResponse;

    if (newChatButton) {
        newChatButton.disabled = isLeadGateOpen || isWaitingForResponse;
    }

    if (isLeadGateOpen) {
        leadNameInput?.focus();
    } else if (!isWaitingForResponse) {
        chatInput.focus();
    }

    updateSuggestionButtonDisabledStates();
}


function normalizeLeadName(value) {
    return String(value || "").trim().replace(/\s+/g, " ");
}


function isValidLeadName(value) {
    const words = normalizeLeadName(value).split(" ").filter(Boolean);

    if (words.length < 2) {
        return false;
    }

    return words.every((word) =>
        /^[^\W\d_]+(?:[-'][^\W\d_]+)*$/u.test(word)
    );
}


function normalizeLeadPhone(value) {
    return String(value || "").trim();
}


function isValidLeadPhone(value) {
    return /^07[0-9]{8}$/.test(normalizeLeadPhone(value));
}


function setLeadStatus(message = "") {
    if (leadStatus) {
        leadStatus.textContent = message;
    }
}


function validateLeadForm({ showErrors = false } = {}) {
    const validName = isValidLeadName(leadNameInput?.value || "");
    const validPhone = isValidLeadPhone(leadPhoneInput?.value || "");
    const validCookieConsent = true;
    const validPrivacyConsent = true;
    const showNameError = (showErrors || leadNameTouched || leadSubmitAttempted) && !validName;
    const showPhoneError = (showErrors || leadPhoneTouched || leadSubmitAttempted) && !validPhone;
    const showCookieConsentError =
        (showErrors || leadCookieConsentTouched || leadSubmitAttempted) &&
        !validCookieConsent;
    const showPrivacyConsentError =
        (showErrors || leadPrivacyConsentTouched || leadSubmitAttempted) &&
        !validPrivacyConsent;

    if (leadNameError) {
        leadNameError.textContent =
            showNameError
                ? translations[currentLanguage].leadNameError
                : "";
    }

    if (leadPhoneError) {
        leadPhoneError.textContent =
            showPhoneError
                ? translations[currentLanguage].leadPhoneError
                : "";
    }

    if (leadCookieConsentError) {
        leadCookieConsentError.textContent =
            showCookieConsentError
                ? translations[currentLanguage].leadCookieConsentError
                : "";
    }

    if (leadPrivacyConsentError) {
        leadPrivacyConsentError.textContent =
            showPrivacyConsentError
                ? translations[currentLanguage].leadPrivacyConsentError
                : "";
    }

    if (leadSubmitButton) {
        leadSubmitButton.disabled =
            isLeadSubmitting ||
            !validName ||
            !validPhone ||
            !validCookieConsent ||
            !validPrivacyConsent;
    }

    return validName && validPhone && validCookieConsent && validPrivacyConsent;
}


async function checkLeadCaptureStatus() {
    if (!chatbotConfig.leadCaptureEnabled || !leadOverlay) {
        setLeadGateOpen(false);
        return;
    }

    setLeadGateOpen(true);
    setLeadStatus(translations[currentLanguage].leadChecking);
    validateLeadForm();

    try {
        const url = new URL(
            chatbotConfig.leadStatusEndpoint,
            window.location.origin
        );
        url.searchParams.set("session_id", leadSessionId);
        const response = await fetch(url.toString(), {
            headers: {
                "Accept": "application/json"
            }
        });

        if (!response.ok) {
            throw new Error("Lead status request failed.");
        }

        const payload = await response.json();
        if (!payload.required || payload.captured) {
            setLeadGateOpen(false);
            setLeadStatus("");
            return;
        }

        setLeadStatus("");
        setLeadGateOpen(true);
    } catch {
        setLeadStatus("");
        setLeadGateOpen(true);
    }
}


async function submitLeadCapture() {
    leadSubmitAttempted = true;

    if (isLeadSubmitting || !validateLeadForm()) {
        return;
    }

    isLeadSubmitting = true;
    validateLeadForm();
    setLeadStatus(translations[currentLanguage].leadSaving);

    try {
        const response = await fetch(chatbotConfig.leadSubmitEndpoint, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            body: JSON.stringify({
                session_id: leadSessionId,
                name: normalizeLeadName(leadNameInput.value),
                phone: normalizeLeadPhone(leadPhoneInput.value),
                cookie_consent_accepted: true,
                privacy_consent_accepted: true
            })
        });

        if (!response.ok) {
            const payload = await response.json().catch(() => ({}));
            throw new Error(payload.detail || translations[currentLanguage].leadSubmitError);
        }

        setLeadStatus("");
        setLeadGateOpen(false);
    } catch (error) {
        setLeadStatus(error.message || translations[currentLanguage].leadSubmitError);
    } finally {
        isLeadSubmitting = false;
        validateLeadForm();
    }
}


function removeVisibleSources(container = document) {
    container
        .querySelectorAll(
            ".sources, .sources-label, .source-card"
        )
        .forEach((element) => {
            element.remove();
        });
}


function removeFollowUpBlocks(container = document) {
    container
        .querySelectorAll(".followup-block")
        .forEach((element) => {
            element.remove();
        });
}


function removeMediaBlocks(container = document) {
    container
        .querySelectorAll(".media-block")
        .forEach((element) => {
            element.remove();
        });
}


function createImageMediaCard(mediaItem) {
    const figure = document.createElement("figure");
    figure.className = "media-card media-card-image";

    const imageButton = document.createElement("button");
    imageButton.type = "button";
    imageButton.className = "media-image-button";
    imageButton.setAttribute("aria-label", `Open image: ${mediaItem.label}`);

    const image = document.createElement("img");
    image.alt = mediaItem.alt_text || mediaItem.label;
    image.loading = "lazy";

    const loadingStatus = document.createElement("div");
    loadingStatus.className = "media-image-status";
    loadingStatus.textContent = "Loading image...";
    loadingStatus.setAttribute("role", "status");

    let fallbackAttempted = false;
    let settled = false;
    const timeoutId = window.setTimeout(() => {
        if (settled) {
            return;
        }
        settled = true;
        image.removeAttribute("src");
        image.style.display = "none";
        loadingStatus.textContent = "Image unavailable";
    }, 10000);

    image.onload = () => {
        if (settled) {
            return;
        }
        settled = true;
        window.clearTimeout(timeoutId);
        loadingStatus.remove();
        imageButton.hidden = false;
    };

    image.onerror = () => {
        if (
            !fallbackAttempted &&
            mediaItem.fallback_url &&
            mediaItem.fallback_url !== image.src
        ) {
            fallbackAttempted = true;
            image.src = mediaItem.fallback_url;
            return;
        }
        if (settled) {
            return;
        }
        settled = true;
        window.clearTimeout(timeoutId);
        image.style.display = "none";
        loadingStatus.textContent = "Image unavailable";
    };

    figure.appendChild(loadingStatus);
    imageButton.appendChild(image);
    imageButton.addEventListener("click", () => openMediaLightbox(mediaItem));
    figure.appendChild(imageButton);

    image.src = mediaItem.url;

    return figure;
}


let activeLightboxTrigger = null;


function closeMediaLightbox() {
    const lightbox = document.querySelector(".media-lightbox");
    if (!lightbox) {
        return;
    }
    lightbox.remove();
    document.removeEventListener("keydown", handleLightboxKeydown);
    if (activeLightboxTrigger && typeof activeLightboxTrigger.focus === "function") {
        activeLightboxTrigger.focus();
    }
    activeLightboxTrigger = null;
}


function handleLightboxKeydown(event) {
    if (event.key === "Escape") {
        closeMediaLightbox();
    }
}


function openMediaLightbox(mediaItem) {
    closeMediaLightbox();
    activeLightboxTrigger = document.activeElement;

    const overlay = document.createElement("div");
    overlay.className = "media-lightbox";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");

    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "media-lightbox-close";
    closeButton.textContent = "×";
    closeButton.setAttribute("aria-label", "Close image");
    closeButton.addEventListener("click", closeMediaLightbox);

    const image = document.createElement("img");
    image.src = mediaItem.url;
    image.alt = mediaItem.alt_text || mediaItem.label;

    overlay.appendChild(closeButton);
    overlay.appendChild(image);
    overlay.addEventListener("click", (event) => {
        if (event.target === overlay) {
            closeMediaLightbox();
        }
    });
    document.body.appendChild(overlay);
    document.addEventListener("keydown", handleLightboxKeydown);
    closeButton.focus();
}


function createVideoMediaCard(mediaItem) {
    const figure = document.createElement("figure");
    figure.className = "media-card media-card-video";

    const video = document.createElement("video");
    video.controls = true;
    video.preload = "metadata";
    video.src = mediaItem.url;

    video.style.maxWidth = "100%";
    video.style.borderRadius = "14px";
    video.style.display = "block";
    video.style.marginTop = "10px";
    video.style.boxShadow = "0 10px 28px rgba(0, 0, 0, 0.18)";

    const caption = document.createElement("figcaption");

    const link = document.createElement("a");
    link.href = mediaItem.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = mediaItem.label || "Open video source";

    caption.appendChild(link);

    caption.style.fontSize = "0.85rem";
    caption.style.opacity = "0.85";
    caption.style.marginTop = "8px";

    figure.appendChild(video);
    figure.appendChild(caption);

    return figure;
}


function createMediaBlock(mediaItems) {
    const normalizedItems = mergeMediaItems(mediaItems);

    if (!normalizedItems.length) {
        return null;
    }

    const block = document.createElement("div");
    block.className = "media-block";

    block.style.marginTop = "12px";
    block.style.display = "grid";
    block.style.gap = "12px";

    for (const mediaItem of normalizedItems) {
        if (mediaItem.type === "image") {
            block.appendChild(createImageMediaCard(mediaItem));
        }

        if (mediaItem.type === "video") {
            block.appendChild(createVideoMediaCard(mediaItem));
        }
    }

    return block;
}


function renderMediaItems(state, mediaItems = []) {
    removeMediaBlocks(state.article);

    const block = createMediaBlock(mediaItems);

    if (!block) {
        state.mediaItems = [];
        return;
    }

    state.mediaItems = mergeMediaItems(mediaItems);

    if (state.cursor && state.cursor.isConnected) {
        state.bubble.insertBefore(block, state.cursor);
    } else {
        state.bubble.appendChild(block);
    }

    scrollToLatestMessage();
}


function renderStaticMediaItems(bubble, mediaItems = []) {
    const block = createMediaBlock(mediaItems);

    if (block) {
        bubble.appendChild(block);
    }
}


function isSalesCallbackStarterItem(item) {
    return (
        item?.id === "request_sales_callback" ||
        item?.type === "request_sales_callback"
    );
}


function isContactStarterItem(item) {
    return item?.id === "contact_us" || item?.type === "contact_us";
}


function updateSuggestionButtonDisabledStates() {
    if (!suggestionList) {
        return;
    }

    suggestionList.querySelectorAll(".suggestion-button").forEach((button) => {
        const isPendingCallbackAction =
            hasPendingSalesCallback &&
            button.dataset.actionId === "request_sales_callback";
        const disabled =
            isWaitingForResponse ||
            isLeadGateOpen ||
            starterActionInFlight ||
            isPendingCallbackAction;

        button.disabled = disabled;
        button.setAttribute("aria-disabled", String(disabled));
        button.classList.toggle(
            "is-loading",
            starterActionInFlight && button === activeStarterButton
        );
    });
}


function normalizedWebsiteHref(value) {
    const website = String(value || "").trim();
    if (!website) {
        return "";
    }
    return /^https?:\/\//i.test(website) ? website : `https://${website}`;
}


function contactDetailValue(details, key, fallback = "") {
    return String(details?.[key] || fallback || "").trim();
}


function appendContactLink(parent, { label, value, href, phone = false }) {
    if (!value) {
        return;
    }

    const row = document.createElement("div");
    row.className = "contact-card-row";

    const labelElement = document.createElement("span");
    labelElement.className = "contact-card-label";
    labelElement.textContent = label;

    const valueElement = document.createElement("a");
    valueElement.className = phone ? "contact-card-value phone-number" : "contact-card-value";
    valueElement.href = href;
    valueElement.textContent = value;
    if (phone) {
        valueElement.dir = "ltr";
    }
    if (!href.startsWith("tel:") && !href.startsWith("mailto:")) {
        valueElement.target = "_blank";
        valueElement.rel = "noopener noreferrer";
    }

    row.appendChild(labelElement);
    row.appendChild(valueElement);
    parent.appendChild(row);
}


function appendContactText(parent, { label, value }) {
    if (!value) {
        return;
    }

    const row = document.createElement("div");
    row.className = "contact-card-row";

    const labelElement = document.createElement("span");
    labelElement.className = "contact-card-label";
    labelElement.textContent = label;

    const valueElement = document.createElement("span");
    valueElement.className = "contact-card-value";
    valueElement.textContent = value;

    row.appendChild(labelElement);
    row.appendChild(valueElement);
    parent.appendChild(row);
}


function appendContactCard() {
    const details = chatbotConfig.contactDetails || {};
    const email = contactDetailValue(details, "email");
    const customerServicePhone = contactDetailValue(details, "customer_service_phone");
    const telephone = contactDetailValue(details, "telephone");
    const website = contactDetailValue(details, "website");
    const address = currentLanguage === "ar"
        ? contactDetailValue(details, "address_ar", details.address_en)
        : contactDetailValue(details, "address_en", details.address_ar);

    const article = document.createElement("article");
    article.className = "message assistant-message contact-card-message";
    article.dir = currentLanguage === "ar" ? "rtl" : "ltr";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble contact-card";

    const title = document.createElement("strong");
    title.className = "contact-card-title";
    title.textContent = translations[currentLanguage].contactCardTitle;
    bubble.appendChild(title);

    appendContactLink(bubble, {
        label: translations[currentLanguage].contactEmail,
        value: email,
        href: `mailto:${email}`
    });
    appendContactLink(bubble, {
        label: translations[currentLanguage].contactCustomerService,
        value: customerServicePhone,
        href: telHref(customerServicePhone),
        phone: true
    });
    appendContactLink(bubble, {
        label: translations[currentLanguage].contactTelephone,
        value: telephone,
        href: telHref(telephone),
        phone: true
    });
    appendContactLink(bubble, {
        label: translations[currentLanguage].contactWebsite,
        value: website,
        href: normalizedWebsiteHref(website)
    });
    appendContactText(bubble, {
        label: translations[currentLanguage].contactAddress,
        value: address
    });

    article.appendChild(bubble);
    chatMessages.appendChild(article);
    scrollToLatestMessage();
    return article;
}


function finishStarterInteraction() {
    starterActionInFlight = false;
    activeStarterButton = null;
    updateSuggestionButtonDisabledStates();
}


function renderSalesCallbackAction(bubble, actionOrLanguage) {
    if (!chatbotConfig.salesCallbackEndpoint) {
        return;
    }
    if (bubble.querySelector(".callback-action")) {
        return;
    }

    const action = typeof actionOrLanguage === "object"
        ? normalizeSalesCallbackAction(actionOrLanguage)
        : normalizeSalesCallbackAction({
              type: "request_sales_callback",
              language: actionOrLanguage || currentLanguage
          });
    if (!action) {
        return;
    }
    const lang = action.language;

    const actionWrapper = document.createElement("div");
    actionWrapper.className = "callback-action";
    actionWrapper.dataset.responseLanguage = lang;
    actionWrapper.dataset.actionType = action.type;
    actionWrapper.dataset.actionLabel = action.label;

    const button = document.createElement("button");
    button.type = "button";
    button.className = "callback-action-button";
    button.textContent = action.label;
    button.disabled = hasPendingSalesCallback;
    button.setAttribute("aria-disabled", String(hasPendingSalesCallback));
    button.addEventListener("click", () => {
        showSalesCallbackConfirmation({ responseLanguage: lang });
    });

    actionWrapper.appendChild(button);
    bubble.appendChild(actionWrapper);
}


function appendSalesCallbackPrompt({ onCancel, onComplete, responseLanguage } = {}) {
    const existingConfirmation = chatMessages.querySelector(
        ".callback-confirmation-message"
    );
    if (existingConfirmation) {
        scrollToLatestMessage();
        return false;
    }

    const lang = responseLanguage || currentLanguage;

    const article = document.createElement("article");
    article.className = "message assistant-message callback-confirmation-message";
    article.dir = lang === "ar" ? "rtl" : "ltr";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble callback-confirmation";

    const title = document.createElement("strong");
    title.className = "callback-confirmation-title";
    title.textContent = translations[lang].callbackTitle;

    const prompt = document.createElement("p");
    prompt.textContent = translations[lang].callbackPrompt;

    const form = document.createElement("form");
    form.className = "callback-message-form";

    const messageLabel = document.createElement("label");
    messageLabel.className = "callback-message-label";
    messageLabel.textContent = translations[lang].callbackMessageLabel;

    const messageInput = document.createElement("textarea");
    messageInput.className = "callback-message-input";
    messageInput.maxLength = 1000;
    messageInput.rows = 4;
    messageInput.dir = lang === "ar" ? "rtl" : "ltr";
    messageInput.placeholder = translations[lang].callbackMessagePlaceholder;

    const messageError = document.createElement("p");
    messageError.className = "callback-message-error";
    messageError.setAttribute("role", "alert");

    const actions = document.createElement("div");
    actions.className = "callback-confirmation-actions";

    const confirmButton = document.createElement("button");
    confirmButton.type = "submit";
    confirmButton.className = "callback-confirm-button";
    confirmButton.textContent = translations[lang].callbackConfirm;

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "callback-cancel-button";
    cancelButton.textContent = translations[lang].callbackCancel;

    messageLabel.appendChild(messageInput);
    form.appendChild(messageLabel);
    form.appendChild(messageError);
    actions.appendChild(confirmButton);
    actions.appendChild(cancelButton);
    form.appendChild(actions);
    bubble.appendChild(title);
    bubble.appendChild(prompt);
    bubble.appendChild(form);
    article.appendChild(bubble);
    chatMessages.appendChild(article);
    messageInput.focus();
    scrollToLatestMessage();

    cancelButton.addEventListener("click", () => {
        article.remove();
        onCancel?.();
    });

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        const clientMessage = messageInput.value.trim();
        if (clientMessage.length > 1000) {
            messageError.textContent = translations[lang].callbackMessageTooLong;
            return;
        }
        messageError.textContent = "";
        submitSalesCallbackRequest({
            article,
            confirmButton,
            cancelButton,
            messageInput,
            clientMessage,
            onComplete,
            callbackLanguage: lang
        });
    });

    return true;
}


function showSalesCallbackConfirmation(options = {}) {
    if (isWaitingForResponse || isLeadGateOpen || hasPendingSalesCallback) {
        return false;
    }

    return appendSalesCallbackPrompt({
        ...options,
        responseLanguage: options.responseLanguage || currentLanguage
    });
}


async function submitSalesCallbackRequest({
    article,
    confirmButton,
    cancelButton,
    messageInput,
    clientMessage = "",
    onComplete,
    callbackLanguage
}) {
    if (!chatbotConfig.salesCallbackEndpoint || confirmButton.disabled) {
        return;
    }

    const lang = callbackLanguage || currentLanguage;

    confirmButton.disabled = true;
    cancelButton.disabled = true;
    if (messageInput) {
        messageInput.disabled = true;
    }
    confirmButton.textContent = translations[lang].callbackSubmitting;

    try {
        const url = new URL(
            chatbotConfig.salesCallbackEndpoint,
            window.location.origin
        );
        url.searchParams.set("language", lang);

        const response = await fetch(url.toString(), {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                session_id: chatbotConfig.leadCaptureEnabled
                    ? leadSessionId
                    : sessionId,
                client_message: clientMessage.slice(0, 1000)
            })
        });

        const payload = await response.json().catch(() => ({}));

        if (!response.ok) {
            throw new Error(
                payload.detail || translations[lang].callbackError
            );
        }

        article.remove();
        hasPendingSalesCallback = true;
        appendMessage(
            "assistant",
            payload.message || translations[lang].callbackSuccess
        );
    } catch (error) {
        confirmButton.disabled = false;
        cancelButton.disabled = false;
        if (messageInput) {
            messageInput.disabled = false;
            messageInput.focus();
        }
        confirmButton.textContent = translations[lang].callbackConfirm;
        appendMessage(
            "assistant",
            error.message || translations[lang].callbackError,
            { disclaimer: true }
        );
    } finally {
        onComplete?.();
        updateSuggestionButtonDisabledStates();
    }
}


function appendMessage(role, text, options = {}) {
    const parsed =
        role === "assistant"
            ? parseAssistantContent(text, options.media || [])
            : {
                  text,
                  media: []
              };

    const cleanedText =
        role === "assistant"
            ? parsed.text
            : text;

    const article = document.createElement("article");

    article.className = `message ${
        role === "user" ? "user-message" : "assistant-message"
    }`;

    if (options.disclaimer) {
        article.classList.add("disclaimer-message");
    }

    article.dir = containsArabic(cleanedText) ? "rtl" : "ltr";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";

    const paragraph = document.createElement("p");
    appendPhoneIsolatedText(paragraph, cleanedText);

    bubble.appendChild(paragraph);

    if (role === "assistant") {
        renderStaticMediaItems(bubble, parsed.media);
    }

    article.appendChild(bubble);

    chatMessages.appendChild(article);
    scrollToLatestMessage();

    return article;
}


function showWelcomeMessage() {
    if (!welcomeMessageTemplate) {
        appendMessage(
            "assistant",
            translations[currentLanguage].welcome
        );
        return;
    }

    const clonedWelcomeArticle = welcomeMessageTemplate.cloneNode(true);

    welcomeMessage = clonedWelcomeArticle.querySelector(
        "#welcome-message"
    );

    if (welcomeMessage) {
        welcomeMessage.textContent =
            translations[currentLanguage].welcome;
    }

    clonedWelcomeArticle.dir =
        currentLanguage === "ar" ? "rtl" : "ltr";

    chatMessages.appendChild(clonedWelcomeArticle);

    removeVisibleSources(clonedWelcomeArticle);
    removeFollowUpBlocks(clonedWelcomeArticle);
    scrollToLatestMessage();
}


function startNewChat() {
    if (isWaitingForResponse) {
        return;
    }

    conversationMemory = [];
    sessionId = createSessionId();

    try {
        localStorage.setItem(SESSION_ID_STORAGE_KEY, sessionId);
        sessionStorage.removeItem(MEMORY_STORAGE_KEY);
        sessionStorage.removeItem(EVIDENCE_STORAGE_KEY);
        sessionStorage.removeItem(LEGACY_EVIDENCE_STORAGE_KEY);
    } catch {
        /*
            The visible chat can still reset normally.
        */
    }

    chatMessages.innerHTML = "";
    evidenceMemory = [];

    showWelcomeMessage();

    chatInput.value = "";
    resizeInput();
    chatInput.focus();
}


function restoreConversation() {
    if (conversationMemory.length === 0) {
        return;
    }

    if (welcomeMessage) {
        const currentWelcomeArticle =
            welcomeMessage.closest(".message");

        if (currentWelcomeArticle) {
            currentWelcomeArticle.remove();
        }
    }

    for (const turn of conversationMemory) {
        appendMessage(turn.role, turn.content);
    }

    removeVisibleSources(chatMessages);
    removeFollowUpBlocks(chatMessages);
}


function createStreamingAssistantMessage(initialStatus) {
    const article = document.createElement("article");

    article.className =
        "message assistant-message streaming-message";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";

    const paragraph = document.createElement("p");
    paragraph.className = "stream-status";
    paragraph.textContent = initialStatus;

    const cursor = document.createElement("span");
    cursor.className = "streaming-cursor";
    cursor.textContent = "\u258b";

    bubble.appendChild(paragraph);
    bubble.appendChild(cursor);

    article.appendChild(bubble);
    chatMessages.appendChild(article);

    scrollToLatestMessage();

    return {
        article,
        bubble,
        paragraph,
        cursor,
        hasText: false,
        rawAnswer: "",
        mediaItems: [],
        evidenceBundle: null,
        hasSalesCallbackAction: false,
        salesCallbackLanguage: null,
        salesCallbackAction: null,
        responseLanguage: null
    };
}


function setStreamingStatus(state, message) {
    if (state.hasText) {
        return;
    }

    state.paragraph.textContent = message;
    scrollToLatestMessage();
}


function appendStreamingDelta(state, text) {
    if (!text) {
        return;
    }

    state.rawAnswer += text;

    const match = /\[\[sales_callback_action(?::([a-z]+))?\]\]/.exec(state.rawAnswer);
    if (match) {
        state.hasSalesCallbackAction = true;
        if (match[1]) {
            state.salesCallbackLanguage = match[1];
        }
        state.salesCallbackAction = normalizeSalesCallbackAction({
            type: "request_sales_callback",
            language: state.salesCallbackLanguage
        });
    }

    if (!state.responseLanguage && text.trim()) {
        state.responseLanguage = containsArabic(state.rawAnswer) ? "ar" : "en";
    }

    const visibleText = cleanVisibleAssistantText(
        state.rawAnswer
    );

    if (!state.hasText && visibleText) {
        state.hasText = true;
        state.paragraph.classList.remove("stream-status");
    }

    appendPhoneIsolatedText(state.paragraph, visibleText);

    if (containsArabic(visibleText)) {
        state.article.dir = "rtl";
    }

    removeVisibleSources(state.article);
    removeFollowUpBlocks(state.article);
    scrollToLatestMessage();
}


function addStreamingSources(state, mediaItems = []) {
    /*
        Sources are still retrieved and validated internally.
        They are intentionally never displayed to clients.

        Media evidence is different:
        it is displayed only when the backend explicitly sends
        approved image/video evidence.
    */
    removeVisibleSources(state.article);

    const mergedMedia = mergeMediaItems(
        state.mediaItems,
        mediaItems
    );

    if (mergedMedia.length) {
        renderMediaItems(state, mergedMedia);
    }
}


function replaceStreamingMessage(
    state,
    answer,
    disclaimer = false,
    mediaItems = []
) {
    const parsed = parseAssistantContent(answer, mediaItems);

    state.hasText = true;
    state.rawAnswer = parsed.text;
    state.hasSalesCallbackAction = parsed.hasSalesCallbackAction;
    state.salesCallbackAction = parsed.salesCallbackAction;
    if (parsed.salesCallbackLanguage) {
        state.salesCallbackLanguage = parsed.salesCallbackLanguage;
    }
    state.responseLanguage = containsArabic(parsed.text) ? "ar" : "en";

    state.paragraph.classList.remove("stream-status");
    appendPhoneIsolatedText(state.paragraph, parsed.text);

    state.article.dir = containsArabic(parsed.text)
        ? "rtl"
        : "ltr";

    state.article.classList.toggle(
        "disclaimer-message",
        Boolean(disclaimer)
    );

    addStreamingSources(state, parsed.media);
    removeFollowUpBlocks(state.article);
    scrollToLatestMessage();
}


function finishStreamingMessage(state) {
    state.cursor.remove();
    state.article.classList.remove("streaming-message");

    const parsed = parseAssistantContent(
        state.rawAnswer || state.paragraph.textContent,
        state.mediaItems
    );

    appendPhoneIsolatedText(state.paragraph, parsed.text);

    removeVisibleSources(state.article);
    removeFollowUpBlocks(state.article);

    if (parsed.media.length) {
        renderMediaItems(state, parsed.media);
    }
    if (parsed.salesCallbackLanguage) {
        state.salesCallbackLanguage = parsed.salesCallbackLanguage;
    }
    if (parsed.salesCallbackAction) {
        state.salesCallbackAction = parsed.salesCallbackAction;
    }
    if (state.salesCallbackAction) {
        renderSalesCallbackAction(state.bubble, state.salesCallbackAction);
    }

    scrollToLatestMessage();
}


function submitQuestion(question, options = {}) {
    if (isWaitingForResponse || isLeadGateOpen) {
        return;
    }

    chatInput.value = question;
    resizeInput();
    chatInput.focus();
    sendMessage(question, options);
}


function renderSuggestions() {
    suggestionList.innerHTML = "";

    for (
        const suggestion of translations[currentLanguage].suggestions
    ) {
        const button = document.createElement("button");
        const item =
            typeof suggestion === "string"
                ? { id: "", type: "question", label: suggestion }
                : suggestion;

        button.type = "button";
        button.className = "suggestion-button";
        button.textContent = item.label;
        button.dir = containsArabic(item.label) ? "rtl" : "ltr";
        button.dataset.actionId = item.id || "";
        button.dataset.starterType = item.type || "question";

        button.addEventListener("click", () => {
            handleSuggestionSelection(item, button);
        });

        suggestionList.appendChild(button);
    }

    updateSuggestionButtonDisabledStates();
}


function handleSuggestionSelection(item, button) {
    if (
        starterActionInFlight ||
        isWaitingForResponse ||
        isLeadGateOpen ||
        button.disabled
    ) {
        return;
    }

    starterActionInFlight = true;
    activeStarterButton = button;
    updateSuggestionButtonDisabledStates();

    if (isSalesCallbackStarterItem(item)) {
        appendMessage("user", item.label);
        rememberTurn("user", item.label);
        const shown = showSalesCallbackConfirmation({
            onCancel: finishStarterInteraction,
            onComplete: finishStarterInteraction
        });
        if (!shown) {
            finishStarterInteraction();
        }
        return;
    }

    if (isContactStarterItem(item)) {
        appendMessage("user", item.label);
        rememberTurn("user", item.label);
        appendContactCard();
        finishStarterInteraction();
        return;
    }

    submitQuestion(item.label, {
        fromStarter: true,
        starterActionId: item.id || ""
    });
}


function updateLanguage(language) {
    currentLanguage = language;

    document.documentElement.lang = language;
    document.documentElement.dir =
        language === "ar" ? "rtl" : "ltr";

    document.querySelectorAll("[data-i18n]").forEach((element) => {
        const key = element.dataset.i18n;

        if (translations[language][key]) {
            element.textContent = translations[language][key];
        }
    });

    if (welcomeMessage?.isConnected) {
        welcomeMessage.textContent =
            translations[language].welcome;

        const currentWelcomeArticle =
            welcomeMessage.closest(".message");

        if (currentWelcomeArticle) {
            currentWelcomeArticle.dir =
                language === "ar" ? "rtl" : "ltr";
        }
    }

    chatInput.placeholder = translations[language].placeholder;

    chatInput.setAttribute(
        "aria-label",
        translations[language].placeholder
    );

    if (leadNameInput) {
        leadNameInput.placeholder = translations[language].leadNamePlaceholder;
    }

    if (leadPhoneInput) {
        leadPhoneInput.placeholder = translations[language].leadPhonePlaceholder;
    }

    document.querySelectorAll(".language-button").forEach((button) => {
        button.classList.toggle(
            "active",
            button.dataset.language === language
        );
    });

    renderSuggestions();
    validateLeadForm({
        showErrors: Boolean(
            leadNameError?.textContent ||
            leadPhoneError?.textContent ||
            leadCookieConsentError?.textContent ||
            leadPrivacyConsentError?.textContent
        ),
    });
}


function handleStreamEvent(event, state) {
    if (event.type === "status") {
        setStreamingStatus(state, event.message);
        return;
    }

    if (event.type === "delta") {
        appendStreamingDelta(state, event.text);
        return;
    }

    if (event.type === "sources") {
        if (event.evidence_bundle) {
            state.evidenceBundle = event.evidence_bundle;
        }

        addStreamingSources(state, event.media || []);
        return;
    }

    if (event.type === "replace") {
        if (event.evidence_bundle) {
            state.evidenceBundle = event.evidence_bundle;
        }

        replaceStreamingMessage(
            state,
            event.answer,
            Boolean(event.disclaimer),
            event.media || []
        );
        return;
    }

    if (event.type === "action") {
        const action = normalizeSalesCallbackAction(event.action);
        if (action) {
            state.hasSalesCallbackAction = true;
            state.salesCallbackLanguage = action.language;
            state.salesCallbackAction = action;
            renderSalesCallbackAction(state.bubble, action);
        }
        return;
    }

    if (event.type === "error") {
        replaceStreamingMessage(
            state,
            event.message ||
                translations[currentLanguage].serviceError,
            true
        );
        return;
    }

    if (event.type === "done") {
        return;
    }
}


function processStreamLine(line, state) {
    if (!line.trim()) {
        return;
    }

    try {
        const event = JSON.parse(line);
        handleStreamEvent(event, state);
    } catch {
        /*
            Ignore incomplete or malformed stream fragments safely.
        */
    }
}


async function sendMessage(message, options = {}) {
    if (isWaitingForResponse) {
        return;
    }

    /*
        Important:
        Build history BEFORE remembering the current user message.
        The backend already receives the current message separately.
    */
    const backendHistoryBeforeRequest = getHistoryForRequest();

    appendMessage("user", message);
    rememberTurn("user", message);

    chatInput.value = "";
    resizeInput();

    setLoadingState(true);

    const streamState = createStreamingAssistantMessage(
        translations[currentLanguage].searching
    );

    try {
        const response = await fetch(
            chatbotConfig.streamEndpoint || "/api/chat/stream",
            {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message,
                session_id: sessionId,
                lead_session_id: chatbotConfig.leadCaptureEnabled
                    ? leadSessionId
                    : undefined,
                starter_action_id: options.starterActionId || undefined,
                language: currentLanguage,
                history: backendHistoryBeforeRequest,
                evidence_history: getEvidenceHistoryForRequest()
            })
            }
        );

        if (!response.ok) {
            const errorText = await response.text();

            throw new Error(
                errorText ||
                    translations[currentLanguage].serviceError
            );
        }

        if (!response.body) {
            throw new Error(
                translations[currentLanguage].serviceError
            );
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");

        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();

            if (done) {
                break;
            }

            buffer += decoder.decode(value, {
                stream: true
            });

            const lines = buffer.split("\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
                processStreamLine(line, streamState);
            }
        }

        buffer += decoder.decode();

        if (buffer.trim()) {
            processStreamLine(buffer, streamState);
        }
    } catch (error) {
        replaceStreamingMessage(
            streamState,
            error.message ||
                translations[currentLanguage].serviceError,
            true
        );
    } finally {
        finishStreamingMessage(streamState);

        const finalAssistantAnswer = cleanMemoryContent(
            streamState.paragraph.textContent
        );

        if (finalAssistantAnswer) {
            rememberTurn("assistant", finalAssistantAnswer);
        }

        if (streamState.evidenceBundle) {
            rememberEvidenceBundle(streamState.evidenceBundle);
        }

        setLoadingState(false);
        if (options.fromStarter) {
            finishStarterInteraction();
        }
    }
}


chatForm.addEventListener("submit", (event) => {
    event.preventDefault();

    const message = chatInput.value.trim();

    if (!message || isWaitingForResponse || isLeadGateOpen) {
        return;
    }

    sendMessage(message);
});


chatInput.addEventListener("input", resizeInput);


chatInput.addEventListener("keydown", (event) => {
    if (
        event.key === "Enter" &&
        !event.shiftKey &&
        !isWaitingForResponse &&
        !isLeadGateOpen
    ) {
        event.preventDefault();
        chatForm.requestSubmit();
    }
});


if (leadForm) {
    leadForm.addEventListener("submit", (event) => {
        event.preventDefault();
        submitLeadCapture();
    });
}


if (leadNameInput) {
    leadNameInput.addEventListener("input", () => {
        setLeadStatus("");
        validateLeadForm();
    });

    leadNameInput.addEventListener("blur", () => {
        leadNameTouched = true;
        validateLeadForm();
    });
}


if (leadPhoneInput) {
    leadPhoneInput.addEventListener("input", () => {
        setLeadStatus("");
        validateLeadForm();
    });

    leadPhoneInput.addEventListener("blur", () => {
        leadPhoneTouched = true;
        validateLeadForm();
    });
}


if (leadCookieConsentInput) {
    leadCookieConsentInput.addEventListener("change", () => {
        leadCookieConsentTouched = true;
        setLeadStatus("");
        validateLeadForm();
    });

    leadCookieConsentInput.addEventListener("blur", () => {
        leadCookieConsentTouched = true;
        validateLeadForm();
    });
}


if (leadPrivacyConsentInput) {
    leadPrivacyConsentInput.addEventListener("change", () => {
        leadPrivacyConsentTouched = true;
        setLeadStatus("");
        validateLeadForm();
    });

    leadPrivacyConsentInput.addEventListener("blur", () => {
        leadPrivacyConsentTouched = true;
        validateLeadForm();
    });
}


if (leadOverlay) {
    leadOverlay.addEventListener("keydown", (event) => {
        if (!isLeadGateOpen || event.key !== "Tab") {
            return;
        }

        const focusable = Array.from(
            leadOverlay.querySelectorAll(
                "button:not(:disabled), input:not(:disabled)"
            )
        );

        if (focusable.length === 0) {
            return;
        }

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    });
}


if (newChatButton) {
    newChatButton.addEventListener("click", startNewChat);
}


document.querySelectorAll(".language-button").forEach((button) => {
    button.addEventListener("click", () => {
        updateLanguage(button.dataset.language);
    });
});


if (chatbotConfig.embedMode) {
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            notifyEmbedParent("close");
        }
    });
}


const initialLanguage =
    chatbotConfig.chatbotType === "campaign" &&
    chatbotConfig.campaignLanguage === "ar"
        ? "ar"
        : "en";

updateLanguage(initialLanguage);
checkLeadCaptureStatus();
restoreConversation();
removeVisibleSources(chatMessages);
removeFollowUpBlocks(chatMessages);
resizeInput();
notifyEmbedParent("ready");
