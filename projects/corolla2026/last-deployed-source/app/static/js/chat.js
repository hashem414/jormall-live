const chatbotConfig = window.CHATBOT_CONFIG || {};
const footerCompanyName =
    chatbotConfig.displayCompanyName || chatbotConfig.companyName || "Markazia Toyota";
const arabicCompanyName =
    chatbotConfig.clientSlug === "central-trade-auto-co-markazia-toyota-jordan"
        ? "المركزية تويوتا"
        : chatbotConfig.companyName;
function configuredFooter(language) {
    const configured =
        language === "ar"
            ? chatbotConfig.footerTextAr
            : chatbotConfig.footerTextEn;

    return (
        configured ||
        `${chatbotConfig.assistantName || "Markazia Toyota Assistant"} \u2013 ${footerCompanyName} \u2022 \u00a9 2026. All rights reserved.`
    );
}

const translations = {
    en: {
        approvedOnly: "",
        heroTitle: "Markazia Toyota Assistant",
        heroSubtitle:
            "Ask questions about Markazia Toyota services, vehicles, and support information.",
        mvpNotice:
            "MVP notice: This is a demonstration chatbot and is not an official Markazia Toyota customer-service channel.",
        chatEyebrow: "",
        chatHeading: "How can we help?",
        sourceOnly: "",
        tryAsking: "Try asking",
        send: "Send \u2192",
        newChat: "New chat",
        footerNote: configuredFooter("en"),
        placeholder: "Ask a question about Markazia Toyota...",
        welcome:
            "Welcome to Markazia Toyota Assistant. Ask me about Markazia Toyota.",
        searching: "Checking available information...",
        serviceError:
            "The Markazia Toyota assistant is temporarily unavailable. Please try again later.",
        leadTitle: "Start your conversation",
        leadSubtitle: "Please enter your name and mobile number to continue to the chatbot.",
        leadNameLabel: "Name",
        leadPhoneLabel: "Mobile Number",
        leadNamePlaceholder: "Ahmed Sami",
        leadPhonePlaceholder: "07XXXXXXXX",
        leadContinue: "Continue",
        leadPrivacy:
            "The contact information you provide will be used to respond to your enquiry and to arrange sales follow-up when you request it.",
        leadNameError: "Please enter your first and last name.",
        leadPhoneError:
            "Please enter a valid 10-digit Jordanian mobile number starting with 07.",
        leadSubmitError: "We could not save your details. Please try again.",
        leadChecking: "Checking your details...",
        leadSaving: "Saving your details...",
        requestCallAction: "Request a Call",
        callbackTitle: "Request a call",
        callbackPrompt:
            "Would you like me to submit a request for the sales team to call you?",
        callbackConfirm: "Confirm request",
        callbackCancel: "Cancel",
        callbackCancelled:
            "The callback request was cancelled. No request was submitted.",
        callbackSubmitting: "Sending request...",
        callbackError: "We could not save your call request. Please try again.",
        suggestions: [
            "What are the main specifications of the 2026 Toyota Corolla Hybrid?",
            "What grades, colours, and features are currently available?",
            "What financing and trade-in options are available?",
            "I would like the sales team to call me."
        ]
    },

    ar: {
        approvedOnly: "",
        heroTitle: "مساعد المركزية تويوتا",
        heroSubtitle:
            "اسأل عن مركبات وخدمات المركزية تويوتا والمعلومات المتاحة عنها.",
        mvpNotice:
            "تنبيه: هذا نموذج أولي تجريبي وليس قناة رسمية لخدمة عملاء المركزية تويوتا.",
        chatEyebrow: "",
        chatHeading: "كيف يمكننا مساعدتك؟",
        sourceOnly: "",
        tryAsking: "جرّب أن تسأل",
        send: "\u0625\u0631\u0633\u0627\u0644 \u2192",
        newChat: "محادثة جديدة",
        footerNote: configuredFooter("ar"),
        placeholder: "اكتب سؤالك عن المركزية تويوتا...",
        welcome:
            "مرحبًا بك في مساعد المركزية تويوتا. اسألني عن المركزية تويوتا.",
        searching: "جارٍ البحث في المعلومات المتاحة...",
        serviceError:
            "مساعد المركزية تويوتا غير متاح مؤقتًا. يرجى المحاولة مرة أخرى لاحقًا.",
        leadTitle: "ابدأ المحادثة",
        leadSubtitle: "يرجى إدخال اسمك ورقم هاتفك للمتابعة إلى الشات بوت.",
        leadNameLabel: "الاسم",
        leadPhoneLabel: "رقم الهاتف",
        leadNamePlaceholder: "أحمد سامي",
        leadPhonePlaceholder: "07XXXXXXXX",
        leadContinue: "متابعة",
        leadPrivacy:
            "سيتم استخدام معلومات الاتصال التي تقدمها للرد على استفسارك وترتيب متابعة فريق المبيعات عند طلبك.",
        leadNameError: "يرجى إدخال الاسم الأول واسم العائلة.",
        leadPhoneError:
            "يرجى إدخال رقم هاتف أردني صحيح مكوّن من 10 أرقام ويبدأ بـ 07.",
        leadSubmitError: "تعذر حفظ بياناتك. يرجى المحاولة مرة أخرى.",
        leadChecking: "جارٍ التحقق من بياناتك...",
        leadSaving: "جارٍ حفظ بياناتك...",
        requestCallAction: "طلب مكالمة",
        callbackTitle: "طلب مكالمة",
        callbackPrompt:
            "هل ترغب في إرسال طلب ليتصل بك فريق المبيعات؟",
        callbackConfirm: "تأكيد الطلب",
        callbackCancel: "إلغاء",
        callbackCancelled:
            "تم إلغاء طلب الاتصال، ولم يتم إرسال أي طلب.",
        callbackSubmitting: "جارٍ إرسال الطلب...",
        callbackError: "تعذر حفظ طلب المكالمة. يرجى المحاولة مرة أخرى.",
        suggestions: [
            "ما المواصفات الرئيسية لتويوتا كورولا هايبرد 2026؟",
            "ما الفئات والألوان والمزايا المتوفرة؟",
            "ما خيارات التمويل واستبدال المركبات المتوفرة؟",
            "أرغب أن يتصل بي فريق المبيعات."
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
    translations.ar.heroTitle = `مساعد ${arabicCompanyName}`;
    translations.ar.heroSubtitle =
        `اسأل عن ${arabicCompanyName} وخدماتها والمعلومات المتاحة عنها.`;
    translations.ar.sourceOnly = "";
    translations.ar.footerNote = configuredFooter("ar");
    translations.ar.placeholder = `اكتب سؤالك عن ${arabicCompanyName}...`;
    translations.ar.welcome =
        `مرحبًا بك في مساعد ${arabicCompanyName}. اسألني عن ${arabicCompanyName}.`;
    translations.ar.searching = "جارٍ البحث في المعلومات المتاحة...";
    translations.ar.serviceError =
        `مساعد ${arabicCompanyName} غير متاح مؤقتًا. يرجى المحاولة لاحقًا.`;
    translations.ar.suggestions = localizedSuggestedQuestions("ar");
    if (chatbotConfig.chatbotType === "campaign") {
        translations.ar.welcome =
            chatbotConfig.openingMessageAr ||
            `مرحبًا بك في مساعد ${arabicCompanyName}. اسألني عن ${chatbotConfig.campaignNameAr || "حملة تويوتا كورولا هايبرد 2026 - القيادة الذكية"}.`;
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
const leadSubmitButton = document.getElementById("prechat-lead-submit");
const leadNameError = document.getElementById("prechat-lead-name-error");
const leadPhoneError = document.getElementById("prechat-lead-phone-error");
const leadStatus = document.getElementById("prechat-lead-status");
let leadNameTouched = false;
let leadPhoneTouched = false;
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
const SALES_CALLBACK_ACTION_TEXT = {
    en: "Request a call from our sales team",
    ar: "اطلب مكالمة من فريق المبيعات"
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
let pendingSalesCallbackConfirmation = false;
let activeSalesCallbackConfirmationArticle = null;
let isSalesCallbackSubmitting = false;
let conversationMemory = loadConversationMemory();
let evidenceMemory = loadEvidenceMemory();


function containsArabic(text) {
    return /[\u0600-\u06FF]/.test(text);
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
        /^\/api\/media\/[0-9a-f-]+\/(?:approved|thumbnail)$/i.test(normalizedUrl) ||
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
    return String(text).replaceAll(SALES_CALLBACK_ACTION_MARKER, "").trim();
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

    return {
        text: cleanVisibleAssistantText(extracted.text),
        media: mergeMediaItems(extracted.media, extraMedia),
        hasSalesCallbackAction: String(text).includes(SALES_CALLBACK_ACTION_MARKER)
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
    const showNameError = (showErrors || leadNameTouched || leadSubmitAttempted) && !validName;
    const showPhoneError = (showErrors || leadPhoneTouched || leadSubmitAttempted) && !validPhone;

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

    if (leadSubmitButton) {
        leadSubmitButton.disabled =
            isLeadSubmitting ||
            !validName ||
            !validPhone;
    }

    return validName && validPhone;
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
                phone: normalizeLeadPhone(leadPhoneInput.value)
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
    image.loading = "eager";
    image.decoding = "async";

    const loadingStatus = document.createElement("div");
    loadingStatus.className = "media-image-status";
    loadingStatus.textContent = "Loading image...";
    loadingStatus.setAttribute("role", "status");

    let fallbackAttempted = false;
    let settled = false;

    const resolveMediaUrl = (value) => {
        if (!value) {
            return "";
        }

        try {
            return new URL(value, window.location.href).href;
        } catch (_error) {
            return value;
        }
    };

    const primaryUrl = resolveMediaUrl(mediaItem.url);
    const fallbackUrl = resolveMediaUrl(mediaItem.fallback_url);

    image.onload = () => {
        if (settled) {
            return;
        }

        settled = true;
        loadingStatus.remove();
        imageButton.hidden = false;
    };

    image.onerror = () => {
        if (
            !fallbackAttempted &&
            fallbackUrl &&
            fallbackUrl !== primaryUrl &&
            fallbackUrl !== image.currentSrc
        ) {
            fallbackAttempted = true;
            image.src = fallbackUrl;
            return;
        }

        if (settled) {
            return;
        }

        settled = true;
        image.style.display = "none";
        loadingStatus.textContent = "Image unavailable";
    };

    figure.appendChild(loadingStatus);
    imageButton.appendChild(image);
    imageButton.addEventListener("click", () => openMediaLightbox(mediaItem));
    figure.appendChild(imageButton);

    image.src = primaryUrl;

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


function updateSuggestionButtonDisabledStates() {
    if (!suggestionList) {
        return;
    }

    suggestionList.querySelectorAll(".suggestion-button").forEach((button) => {
        const isPendingCallbackAction =
            (hasPendingSalesCallback || pendingSalesCallbackConfirmation) &&
            button.dataset.actionId === "request_sales_callback";
        const disabled =
            isWaitingForResponse ||
            isLeadGateOpen ||
            starterActionInFlight ||
            isSalesCallbackSubmitting ||
            isPendingCallbackAction;

        button.disabled = disabled;
        button.setAttribute("aria-disabled", String(disabled));
        button.classList.toggle(
            "is-loading",
            starterActionInFlight && button === activeStarterButton
        );
    });
}


function finishStarterInteraction() {
    starterActionInFlight = false;
    activeStarterButton = null;
    updateSuggestionButtonDisabledStates();
}


function renderSalesCallbackAction(bubble) {
    if (!chatbotConfig.salesCallbackEndpoint) {
        return;
    }

    const actionWrapper = document.createElement("div");
    actionWrapper.className = "callback-action";

    const button = document.createElement("button");
    button.type = "button";
    button.className = "callback-action-button";
    button.textContent = translations[currentLanguage].requestCallAction;
    button.disabled = hasPendingSalesCallback || pendingSalesCallbackConfirmation;
    button.setAttribute("aria-disabled", String(button.disabled));
    button.addEventListener("click", () => {
        showSalesCallbackConfirmation();
    });

    actionWrapper.appendChild(button);
    bubble.appendChild(actionWrapper);
}


function appendSalesCallbackPrompt({ onCancel, onComplete } = {}) {
    const existingConfirmation = chatMessages.querySelector(
        ".callback-confirmation-message"
    );
    if (existingConfirmation) {
        pendingSalesCallbackConfirmation = true;
        activeSalesCallbackConfirmationArticle = existingConfirmation;
        scrollToLatestMessage();
        return false;
    }

    const article = document.createElement("article");
    article.className = "message assistant-message callback-confirmation-message";
    article.dir = currentLanguage === "ar" ? "rtl" : "ltr";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble callback-confirmation";

    const prompt = document.createElement("p");
    prompt.textContent = translations[currentLanguage].callbackPrompt;

    const actions = document.createElement("div");
    actions.className = "callback-confirmation-actions";

    const confirmButton = document.createElement("button");
    confirmButton.type = "button";
    confirmButton.className = "callback-confirm-button";
    confirmButton.textContent = translations[currentLanguage].callbackConfirm;

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "callback-cancel-button";
    cancelButton.textContent = translations[currentLanguage].callbackCancel;

    actions.appendChild(confirmButton);
    actions.appendChild(cancelButton);
    bubble.appendChild(prompt);
    bubble.appendChild(actions);
    article.appendChild(bubble);
    chatMessages.appendChild(article);
    pendingSalesCallbackConfirmation = true;
    activeSalesCallbackConfirmationArticle = article;
    updateSuggestionButtonDisabledStates();
    scrollToLatestMessage();

    cancelButton.addEventListener("click", () => {
        cancelSalesCallbackConfirmation({ article, onCancel, onComplete });
    });

    confirmButton.addEventListener("click", () => {
        submitSalesCallbackRequest({
            article,
            confirmButton,
            cancelButton,
            onComplete
        });
    });

    return true;
}


function isActiveSalesCallbackConfirmation(article) {
    return (
        pendingSalesCallbackConfirmation &&
        article &&
        article === activeSalesCallbackConfirmationArticle &&
        article.isConnected
    );
}


function setSalesCallbackConfirmationButtonsDisabled(article, disabled) {
    article
        ?.querySelectorAll(".callback-confirm-button, .callback-cancel-button")
        .forEach((button) => {
            button.disabled = disabled;
            button.setAttribute("aria-disabled", String(disabled));
        });
}


function cancelSalesCallbackConfirmation({ article, onCancel, onComplete } = {}) {
    const targetArticle = article || activeSalesCallbackConfirmationArticle;

    if (!isActiveSalesCallbackConfirmation(targetArticle)) {
        return;
    }

    setSalesCallbackConfirmationButtonsDisabled(targetArticle, true);
    pendingSalesCallbackConfirmation = false;
    activeSalesCallbackConfirmationArticle = null;
    targetArticle.remove();
    appendMessage("assistant", translations[currentLanguage].callbackCancelled);
    rememberTurn("assistant", translations[currentLanguage].callbackCancelled);
    onCancel?.();
    onComplete?.();
    updateSuggestionButtonDisabledStates();
}


function showSalesCallbackConfirmation(options = {}) {
    if (isWaitingForResponse || isLeadGateOpen) {
        return false;
    }

    return appendSalesCallbackPrompt(options);
}


async function submitSalesCallbackRequest({
    article,
    confirmButton,
    cancelButton,
    onComplete
}) {
    if (
        !chatbotConfig.salesCallbackEndpoint ||
        isSalesCallbackSubmitting ||
        !isActiveSalesCallbackConfirmation(article)
    ) {
        return;
    }

    isSalesCallbackSubmitting = true;
    setSalesCallbackConfirmationButtonsDisabled(article, true);
    if (confirmButton) {
        confirmButton.textContent = translations[currentLanguage].callbackSubmitting;
    }

    try {
        const url = new URL(
            chatbotConfig.salesCallbackEndpoint,
            window.location.origin
        );
        url.searchParams.set("language", currentLanguage);

        const response = await fetch(url.toString(), {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                session_id: chatbotConfig.leadCaptureEnabled
                    ? leadSessionId
                    : sessionId
            })
        });

        const payload = await response.json().catch(() => ({}));

        if (!response.ok) {
            throw new Error(
                payload.detail || translations[currentLanguage].callbackError
            );
        }

        article.remove();
        pendingSalesCallbackConfirmation = false;
        activeSalesCallbackConfirmationArticle = null;
        hasPendingSalesCallback = true;
        appendMessage("assistant", payload.message || "");
        if (payload.message) {
            rememberTurn("assistant", payload.message);
        }
    } catch (error) {
        setSalesCallbackConfirmationButtonsDisabled(article, false);
        if (confirmButton) {
            confirmButton.textContent = translations[currentLanguage].callbackConfirm;
        }
        appendMessage(
            "assistant",
            error.message || translations[currentLanguage].callbackError,
            { disclaimer: true }
        );
    } finally {
        isSalesCallbackSubmitting = false;
        onComplete?.();
        updateSuggestionButtonDisabledStates();
    }
}


function submitSalesCallbackStarter(item) {
    appendMessage("user", item.label);
    rememberTurn("user", item.label);

    if (!chatbotConfig.salesCallbackEndpoint) {
        appendMessage("assistant", translations[currentLanguage].callbackError, {
            disclaimer: true
        });
        finishStarterInteraction();
        return;
    }

    showSalesCallbackConfirmation();
    finishStarterInteraction();
}


function normalizeCallbackDecisionText(message) {
    return normalizeWhitespace(message).toLowerCase();
}


function isCallbackConfirmationText(message) {
    const normalized = normalizeCallbackDecisionText(message);
    const confirmations = [
        "yes",
        "confirm",
        "please do",
        "call me",
        "نعم",
        "تأكيد",
        "موافق",
        "اتصلوا بي"
    ];

    return confirmations.includes(normalized);
}


function isCallbackCancellationText(message) {
    const normalized = normalizeCallbackDecisionText(message);
    const cancellations = [
        "no",
        "cancel",
        "never mind",
        "لا",
        "إلغاء",
        "الغاء",
        "الغي",
        "مش الآن",
        "مش الان"
    ];

    return cancellations.includes(normalized);
}


function isTypedSalesCallbackRequest(message) {
    const normalized = normalizeCallbackDecisionText(message);
    const labels = [
        "i would like the sales team to call me.",
        "i would like the sales team to call me",
        "أرغب أن يتصل بي فريق المبيعات.",
        "أرغب أن يتصل بي فريق المبيعات",
        "call me",
        "اتصلوا بي"
    ];

    return labels.includes(normalized);
}


function handlePendingSalesCallbackDecision(message) {
    if (!pendingSalesCallbackConfirmation) {
        return false;
    }

    if (isSalesCallbackSubmitting) {
        return true;
    }

    const article = activeSalesCallbackConfirmationArticle;

    if (isCallbackConfirmationText(message)) {
        appendMessage("user", message);
        rememberTurn("user", message);
        submitSalesCallbackRequest({
            article,
            confirmButton: article?.querySelector(".callback-confirm-button"),
            cancelButton: article?.querySelector(".callback-cancel-button")
        });
        return true;
    }

    if (isCallbackCancellationText(message)) {
        appendMessage("user", message);
        rememberTurn("user", message);
        cancelSalesCallbackConfirmation({ article });
        return true;
    }

    return false;
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
    paragraph.textContent = cleanedText;

    bubble.appendChild(paragraph);

    if (role === "assistant") {
        renderStaticMediaItems(bubble, parsed.media);
        if (parsed.hasSalesCallbackAction) {
            renderSalesCallbackAction(bubble);
        }
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
        evidenceBundle: null
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

    const visibleText = cleanVisibleAssistantText(
        state.rawAnswer
    );

    if (!state.hasText && visibleText) {
        state.hasText = true;
        state.paragraph.classList.remove("stream-status");
    }

    state.paragraph.textContent = visibleText;

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

    state.paragraph.classList.remove("stream-status");
    state.paragraph.textContent = parsed.text;

    state.article.dir = containsArabic(parsed.text)
        ? "rtl"
        : "ltr";

    state.article.classList.toggle(
        "disclaimer-message",
        Boolean(disclaimer)
    );

    addStreamingSources(state, parsed.media);
    if (parsed.hasSalesCallbackAction) {
        renderSalesCallbackAction(state.bubble);
    }
    removeFollowUpBlocks(state.article);
    scrollToLatestMessage();
}


function finishStreamingMessage(state) {
    state.cursor.remove();
    state.article.classList.remove("streaming-message");

    const parsed = parseAssistantContent(
        state.paragraph.textContent,
        state.mediaItems
    );

    state.paragraph.textContent = parsed.text;

    removeVisibleSources(state.article);
    removeFollowUpBlocks(state.article);

    if (parsed.media.length) {
        renderMediaItems(state, parsed.media);
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
        submitSalesCallbackStarter(item);
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
            leadPhoneError?.textContent
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

    if (handlePendingSalesCallbackDecision(message)) {
        chatInput.value = "";
        resizeInput();
        return;
    }

    if (isTypedSalesCallbackRequest(message)) {
        chatInput.value = "";
        resizeInput();
        submitSalesCallbackStarter({
            id: "request_sales_callback",
            type: "request_sales_callback",
            label: message
        });
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
