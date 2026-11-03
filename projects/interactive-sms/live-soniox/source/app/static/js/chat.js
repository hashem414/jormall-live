const chatbotConfig = window.CHATBOT_CONFIG || {};
const appBasePath = String(chatbotConfig.appBasePath || "").replace(/\/$/, "");

function appUrl(path) {
    if (/^https?:\/\//i.test(path)) {
        return path;
    }
    return `${appBasePath}${path}`;
}

const footerCompanyName =
    chatbotConfig.displayCompanyName || chatbotConfig.companyName || "JorMall";
const arabicCompanyName = "جورمول";
function configuredFooter(language) {
    const configured =
        language === "ar"
            ? chatbotConfig.footerTextAr
            : chatbotConfig.footerTextEn;

    if (configured) {
        return configured;
    }
    if (language === "ar") {
        return `مساعد ${arabicCompanyName} • بدعم من ${arabicCompanyName} • \u00a9 2026. جميع الحقوق محفوظة.`;
    }
    return `${chatbotConfig.assistantName || "JorMall Assistant"} \u2013 ${footerCompanyName} \u2022 Powered by JorMall \u2022 \u00a9 2026. All rights reserved.`;
}

const translations = {
    en: {
        pageTitle: "JorMall Assistant",
        companyLogoAlt: "JorMall logo",
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
        callCompany: "Call JorMall at +962 77 544 4436",
        emailCompany: "Email JorMall at info@jormall.com",
        footerNote: configuredFooter("en"),
        placeholder: "Ask a question about JorMall...",
        welcome:
            "Welcome to JorMall Assistant. Ask me about JorMall.",
        searching: "Checking available information...",
        serviceError:
            "JorMall can assist with messaging services, API integration, OTP messaging and chatbot solutions. Please contact the JorMall team for the technical details and pricing suitable for your business.",
        partialFallback:
            "For additional details or a solution tailored to your business, please contact the JorMall team.",
        leadTitle: "Start your conversation",
        leadSubtitle: "Please enter your name and mobile number to continue to the chatbot.",
        leadNameLabel: "Name",
        leadPhoneLabel: "Mobile Number",
        leadNamePlaceholder: "Ahmed Sami",
        leadPhonePlaceholder: "07XXXXXXXX",
        leadContinue: "Continue",
        leadNoticeIntro:
            "Your contact details will be used to follow up regarding this service.",
        reviewContactNotice:
            "Review information about contact details and browser storage",
        reviewCookieNotice: "Review Cookie Notice",
        reviewPrivacyNotice: "Review Privacy & Data Protection Notice",
        contactNoticeTitle: "Contact Details and Browser Storage Information",
        cookieNoticeTitle: "Cookie and Browser Storage Notice",
        privacyNoticeTitle: "Privacy and Data Protection Notice",
        leadNameError: "Please enter your first and last name.",
        leadPhoneError:
            "Please enter a valid 10-digit Jordanian mobile number starting with 07.",
        leadSubmitError: "We could not save your details. Please try again.",
        leadChecking: "Checking your details...",
        leadSaving: "Saving your details...",
        requestCallAction: "Request a Call",
        callbackTitle: "Request a call",
        callbackPrompt:
            "Would you like our sales team to contact you using the mobile number you provided?",
        callbackConfirm: "Confirm Request",
        callbackCancel: "Cancel",
        callbackSubmitting: "Sending request...",
        callbackError: "We could not save your call request. Please try again.",
        voiceStart: "Start voice message",
        voiceStop: "Stop recording",
        voiceRecording: "Listening. Press again to stop.",
        voiceTranscribing: "Transcribing your voice message...",
        voiceNoSpeech: "No speech was detected. Please try again.",
        voiceError: "Voice input is unavailable. Please try again or type your question.",
        voicePermission: "Allow microphone access in your browser, then try again.",
        voiceSecureContext: "Voice input requires HTTPS or localhost.",
        voiceListeningTitle: "Listening…",
        voiceListeningHint: "Tap the circle when you finish speaking.",
        voiceWarmingTitle: "Getting the microphone ready…",
        voiceWarmingHint: "Start speaking when Listening appears.",
        voiceThinkingTitle: "Understanding…",
        voiceThinkingHint: "I’m preparing the answer from the approved information.",
        voicePreparingTitle: "Preparing voice…",
        voicePreparingHint: "The reply will begin as soon as the first audio is ready.",
        voiceSpeakingTitle: "Speaking…",
        voiceSpeakingHint: "Tap the circle to stop the reply.",
        voiceClose: "Close voice mode",
        voiceDisclosure: "AI-generated voice",
        suggestions: [
            "What is Smart Reach SMS?",
            "Does JorMall provide delivery reports?",
            "What are the free SMS bonus percentages?",
            "What are the contract approval requirements?"
        ]
    },

    ar: {
        pageTitle: "مساعد جورمول",
        companyLogoAlt: "شعار جورمول",
        approvedOnly: "",
        heroTitle: "مساعد جورمول",
        heroSubtitle:
            "اسأل عن خدمات جورمول والسياسات المعتمدة ومعلومات الأسعار وغيرها.",
        chatEyebrow: "",
        chatHeading: "كيف يمكننا مساعدتك؟",
        sourceOnly: "",
        tryAsking: "جرّب أن تسأل",
        send: "\u0625\u0631\u0633\u0627\u0644 \u2192",
        newChat: "محادثة جديدة",
        callCompany: "اتصل بجورمول على الرقم +962 77 544 4436",
        emailCompany: "راسل جورمول على info@jormall.com",
        footerNote: configuredFooter("ar"),
        placeholder: "اكتب سؤالك عن جورمول...",
        welcome:
            "مرحبًا بك في مساعد جورمول. اسألني عن جورمول.",
        searching: "جارٍ البحث في المعلومات المتاحة...",
        serviceError:
            "يسعدنا مساعدتك في خدمات الرسائل داخل الأردن وخارجه، وربط الأنظمة عبر API، ورسائل OTP، وحلول الشات بوت. للحصول على التفاصيل الفنية والأسعار المناسبة لاحتياجات شركتك، يرجى التواصل مع فريق جورمول.",
        partialFallback:
            "للحصول على تفاصيل إضافية أو عرض مناسب لاحتياجات شركتك، يرجى التواصل مع فريق جورمول.",
        leadTitle: "ابدأ المحادثة",
        leadSubtitle: "يرجى إدخال اسمك ورقم هاتفك للمتابعة إلى الشات بوت.",
        leadNameLabel: "الاسم",
        leadPhoneLabel: "رقم الهاتف",
        leadNamePlaceholder: "أحمد سامي",
        leadPhonePlaceholder: "07XXXXXXXX",
        leadContinue: "متابعة",
        leadNoticeIntro:
            "سيتم استخدام بيانات التواصل الخاصة بك للمتابعة بشأن هذه الخدمة.",
        reviewContactNotice:
            "مراجعة معلومات بيانات التواصل والتخزين في المتصفح",
        reviewCookieNotice: "مراجعة إشعار ملفات تعريف الارتباط",
        reviewPrivacyNotice: "مراجعة إشعار الخصوصية وحماية البيانات",
        contactNoticeTitle: "معلومات بيانات التواصل والتخزين في المتصفح",
        cookieNoticeTitle: "إشعار ملفات تعريف الارتباط والتخزين في المتصفح",
        privacyNoticeTitle: "إشعار الخصوصية وحماية البيانات",
        leadNameError: "يرجى إدخال الاسم الأول واسم العائلة.",
        leadPhoneError:
            "يرجى إدخال رقم هاتف أردني صحيح مكوّن من 10 أرقام ويبدأ بـ 07.",
        leadSubmitError: "تعذر حفظ بياناتك. يرجى المحاولة مرة أخرى.",
        leadChecking: "جارٍ التحقق من بياناتك...",
        leadSaving: "جارٍ حفظ بياناتك...",
        requestCallAction: "طلب مكالمة",
        callbackTitle: "طلب مكالمة",
        callbackPrompt:
            "هل ترغب في أن يتواصل معك فريق المبيعات باستخدام رقم الهاتف الذي أدخلته؟",
        callbackConfirm: "تأكيد الطلب",
        callbackCancel: "إلغاء",
        callbackSubmitting: "جارٍ إرسال الطلب...",
        callbackError: "تعذر حفظ طلب المكالمة. يرجى المحاولة مرة أخرى.",
        voiceStart: "بدء رسالة صوتية",
        voiceStop: "إيقاف التسجيل",
        voiceRecording: "جارٍ الاستماع. اضغط مرة أخرى لإيقاف التسجيل.",
        voiceTranscribing: "جارٍ تحويل رسالتك الصوتية إلى نص...",
        voiceNoSpeech: "لم يتم اكتشاف كلام واضح. يرجى المحاولة مرة أخرى.",
        voiceError: "الإدخال الصوتي غير متاح. حاول مرة أخرى أو اكتب سؤالك.",
        voicePermission: "اسمح للمتصفح باستخدام الميكروفون ثم حاول مرة أخرى.",
        voiceSecureContext: "يتطلب الإدخال الصوتي اتصال HTTPS أو localhost.",
        voiceListeningTitle: "أستمع إليك…",
        voiceListeningHint: "اضغط على الدائرة عند الانتهاء من الكلام.",
        voiceWarmingTitle: "جارٍ تجهيز الميكروفون…",
        voiceWarmingHint: "ابدأ الكلام عندما تظهر عبارة أستمع إليك.",
        voiceThinkingTitle: "جارٍ فهم السؤال…",
        voiceThinkingHint: "أُحضّر الإجابة من المعلومات المعتمدة.",
        voicePreparingTitle: "جارٍ تجهيز الصوت…",
        voicePreparingHint: "سيبدأ الرد فور جهوز أول مقطع صوتي.",
        voiceSpeakingTitle: "أتحدث الآن…",
        voiceSpeakingHint: "اضغط على الدائرة لإيقاف الرد.",
        voiceClose: "إغلاق الوضع الصوتي",
        voiceDisclosure: "صوت مولّد بالذكاء الاصطناعي",
        suggestions: [
            "ما هي خدمات الرسائل القصيرة التي تقدمها جورمول؟",
            "هل توفر جورمول تقارير تسليم الرسائل؟",
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
    translations.en.pageTitle = assistantName;
    translations.en.companyLogoAlt = `${chatbotConfig.companyName} logo`;
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
        "JorMall can assist with messaging services, API integration, OTP messaging and chatbot solutions. Please contact the JorMall team for the technical details and pricing suitable for your business.";
    translations.en.suggestions = localizedSuggestedQuestions("en");

    translations.ar.approvedOnly = "";
    translations.ar.pageTitle = `مساعد ${arabicCompanyName}`;
    translations.ar.companyLogoAlt = `شعار ${arabicCompanyName}`;
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
        "يسعدنا مساعدتك في خدمات الرسائل داخل الأردن وخارجه، وربط الأنظمة عبر API، ورسائل OTP، وحلول الشات بوت. للحصول على التفاصيل الفنية والأسعار المناسبة لاحتياجات شركتك، يرجى التواصل مع فريق جورمول.";
    translations.ar.suggestions = localizedSuggestedQuestions("ar");
    if (chatbotConfig.chatbotType === "campaign") {
        translations.ar.welcome =
            chatbotConfig.openingMessageAr ||
            `مرحبًا بك في مساعد ${arabicCompanyName}. اسألني عن ${chatbotConfig.campaignNameAr || arabicCompanyName}.`;
    }
}


const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatMessages = document.getElementById("chat-messages");
const sendButton = document.getElementById("send-button");
const voiceButton = document.getElementById("voice-button");
const voiceStatus = document.getElementById("voice-status");
const voiceExperience = document.getElementById("voice-experience");
const voiceExperienceClose = document.getElementById("voice-experience-close");
const voiceOrbButton = document.getElementById("voice-orb-button");
const voiceExperienceTitle = document.getElementById("voice-experience-title");
const voiceExperienceHint = document.getElementById("voice-experience-hint");
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
const noticeDialogBackdrop = document.getElementById("notice-dialog-backdrop");
const noticeDialog = document.getElementById("notice-dialog");
const noticeDialogTitle = document.getElementById("notice-dialog-title");
const noticeDialogBody = document.getElementById("notice-dialog-body");
const noticeDialogClose = document.getElementById("notice-dialog-close");
let leadNameTouched = false;
let leadPhoneTouched = false;
let leadSubmitAttempted = false;
let cookieNoticeOpened = false;
let privacyNoticeOpened = false;
let noticeReturnFocus = null;

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
const KNOWLEDGE_MEMORY_VERSION = String(
    chatbotConfig.knowledgeVersion || "legacy"
).replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 80);
const MEMORY_STORAGE_KEY =
    `client_chat_session_history_${chatbotConfig.clientSlug || "jormall"}_${KNOWLEDGE_MEMORY_VERSION}`;
const SESSION_ID_STORAGE_KEY =
    `client_chat_session_id_${chatbotConfig.clientSlug || "jormall"}_${KNOWLEDGE_MEMORY_VERSION}`;
const LEAD_SESSION_ID_STORAGE_KEY =
    `client_chat_lead_session_id_${chatbotConfig.clientSlug || "jormall"}_v1`;
const CONVERSATION_ID_STORAGE_KEY =
    `client_chat_conversation_id_${chatbotConfig.clientSlug || "jormall"}_${KNOWLEDGE_MEMORY_VERSION}`;
const SALES_CALLBACK_ACTION_MARKER = "[[sales_callback_action]]";
const SALES_CALLBACK_ACTION_TEXT = {
    en: "Request a call from our sales team",
    ar: "اطلب من فريق المبيعات الاتصال بي"
};
const EVIDENCE_STORAGE_KEY =
    `evidence_history_${chatbotConfig.clientSlug || "jormall"}_${KNOWLEDGE_MEMORY_VERSION}`;
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
let conversationId = localStorage.getItem(CONVERSATION_ID_STORAGE_KEY) || "";
let isLeadGateOpen = Boolean(chatbotConfig.leadCaptureEnabled);
let isLeadSubmitting = false;
let starterActionInFlight = false;
let activeStarterButton = null;
let hasPendingSalesCallback = false;
let conversationMemory = loadConversationMemory();
let evidenceMemory = loadEvidenceMemory();
let mediaRecorder = null;
let voiceStream = null;
let voiceChunks = [];
let voiceStopTimer = null;
let voiceState = "idle";
let voiceRecordingLanguage = "en";
let voiceStopPending = false;
let cancelCurrentRecording = false;
let cancelPendingVoiceReply = false;
function containsArabic(text) {
    return /[\u0600-\u06FF]/.test(text);
}


function detectTextLanguage(text, fallback = "en") {
    const languageText = String(text || "").replace(
        /https?:\/\/[^\s]+|www\.[^\s]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?:\/[^\s]*)?/gi,
        " "
    );
    const words = languageText.match(/\p{L}+(?:['’\-]\p{L}+)*/gu) || [];
    const votes = [];
    for (const word of words) {
        const arabic = (word.match(/[\u0600-\u06FF]/g) || []).length;
        const latin = (word.match(/[A-Za-z]/g) || []).length;
        if (arabic > latin) votes.push("ar");
        else if (latin > arabic) votes.push("en");
    }
    if (!votes.length) return fallback === "ar" ? "ar" : "en";
    const arabicVotes = votes.filter((value) => value === "ar").length;
    const englishVotes = votes.length - arabicVotes;
    if (arabicVotes > englishVotes) return "ar";
    if (englishVotes > arabicVotes) return "en";
    return votes[0];
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


function cleanMediaLabel(label) {
    return normalizeWhitespace(
        label || (currentLanguage === "ar"
            ? `دليل مصدر ${arabicCompanyName}`
            : `${chatbotConfig.companyName || "Client"} source evidence`)
    );
}


function applyMessageLanguage(element, text) {
    const isArabic = containsArabic(text);
    element.classList.toggle("lang-ar", isArabic);
    element.classList.toggle("lang-en", !isArabic);
    element.dir = isArabic ? "rtl" : "ltr";
}


function appendPhoneAwareText(element, text) {
    const phonePattern = /\+?\d[\d\s().-]{5,}\d/g;
    let cursor = 0;

    for (const match of String(text || "").matchAll(phonePattern)) {
        const phoneText = match[0];
        const start = match.index ?? 0;
        const digitCount = (phoneText.match(/\d/g) || []).length;

        if (digitCount < 7) {
            continue;
        }

        element.appendChild(
            document.createTextNode(String(text).slice(cursor, start))
        );

        const phone = document.createElement("bdi");
        phone.className = "message-phone-number";
        phone.dir = "ltr";
        phone.textContent = phoneText;
        element.appendChild(phone);

        cursor = start + phoneText.length;
    }

    element.appendChild(
        document.createTextNode(String(text || "").slice(cursor))
    );
}


function renderAssistantText(element, text) {
    const sourceText = String(text || "");
    const emphasisPattern = /\*\*([^*\n]+)\*\*/g;
    let cursor = 0;

    element.replaceChildren();

    for (const match of sourceText.matchAll(emphasisPattern)) {
        const start = match.index ?? 0;

        appendPhoneAwareText(
            element,
            sourceText.slice(cursor, start).replaceAll("**", "")
        );

        const strong = document.createElement("strong");
        appendPhoneAwareText(strong, match[1]);
        element.appendChild(strong);

        cursor = start + match[0].length;
    }

    appendPhoneAwareText(
        element,
        sourceText.slice(cursor).replaceAll("**", "")
    );
}


function isAllowedImageUrl(url) {
    return (
        /^\/static\/scraped_sources\/(?:[a-z0-9-]+\/)?(?:images|screenshots|document_images)\/.+\.(png|jpg|jpeg|webp|gif)$/i.test(url) ||
        /^https?:\/\/.+\.(png|jpg|jpeg|webp|gif)(?:\?.*)?$/i.test(url)
    );
}


function isAllowedVideoUrl(url) {
    return (
        /^https?:\/\/.+\.(mp4|webm|mov|m4v)(\?.*)?$/i.test(url) ||
        /^\/static\/scraped_sources\/(?:[a-z0-9-]+\/)?videos\/.+\.(mp4|webm|mov|m4v)$/i.test(url)
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
        url,
        label,
        fallback_url:
            type === "image" && fallbackUrl && isAllowedImageUrl(fallbackUrl)
                ? fallbackUrl
                : "",
        description: normalizeWhitespace(item.description || ""),
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

            const key = `${item.type}:${item.url}`;

            if (seen.has(key)) {
                const existing = merged[seen.get(key)];
                for (const [field, value] of Object.entries(item)) {
                    if (!existing[field] && value) {
                        existing[field] = value;
                    }
                }
                continue;
            }

            seen.set(key, merged.length);
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


function browserVoiceInputSupported() {
    const recorderSupported = chatbotConfig.voiceTransport === "openai_webrtc"
        ? Boolean(window.RTCPeerConnection)
        : Boolean(window.MediaRecorder);
    return Boolean(
        chatbotConfig.voiceEnabled &&
        window.isSecureContext &&
        navigator.mediaDevices?.getUserMedia &&
        recorderSupported
    );
}


function setVoiceStatus(message = "") {
    if (voiceStatus) {
        voiceStatus.textContent = message;
    }
}


function setVoiceExperienceState(state) {
    if (!voiceExperience) return;
    const copy = {
        listening: ["voiceListeningTitle", "voiceListeningHint", "voiceStop"],
        warming: ["voiceWarmingTitle", "voiceWarmingHint", "voiceStop"],
        thinking: ["voiceThinkingTitle", "voiceThinkingHint", "voiceClose"],
        preparing: ["voicePreparingTitle", "voicePreparingHint", "voiceClose"],
        speaking: ["voiceSpeakingTitle", "voiceSpeakingHint", "voiceClose"]
    }[state];
    if (!copy) return;

    voiceExperience.hidden = false;
    voiceExperience.dataset.state = state;
    if (voiceExperienceTitle) {
        voiceExperienceTitle.textContent = translations[currentLanguage][copy[0]];
    }
    if (voiceExperienceHint) {
        voiceExperienceHint.textContent = translations[currentLanguage][copy[1]];
    }
    if (voiceOrbButton) {
        voiceOrbButton.setAttribute("aria-label", translations[currentLanguage][copy[2]]);
    }
    if (voiceExperienceClose) {
        voiceExperienceClose.setAttribute("aria-label", translations[currentLanguage].voiceClose);
    }
}


function hideVoiceExperience() {
    if (!voiceExperience) return;
    voiceExperience.hidden = true;
    voiceExperience.dataset.state = "idle";
}


function updateVoiceButton() {
    if (!voiceButton) {
        return;
    }

    const isRecording = voiceState === "recording";
    const isBusy = voiceState === "transcribing";
    voiceButton.dataset.state = voiceState;
    voiceButton.setAttribute("aria-pressed", String(isRecording));
    voiceButton.setAttribute(
        "aria-label",
        translations[currentLanguage][isRecording ? "voiceStop" : "voiceStart"]
    );
    voiceButton.disabled = Boolean(
        (!isRecording && !browserVoiceInputSupported()) ||
        isBusy ||
        isLeadGateOpen ||
        (!isRecording && isWaitingForResponse)
    );
}


function setVoiceComposerLocked(locked) {
    const disabled = Boolean(locked || isWaitingForResponse || isLeadGateOpen);
    sendButton.disabled = disabled;
    chatInput.disabled = disabled;
    if (newChatButton) {
        newChatButton.disabled = disabled;
    }
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
    updateVoiceButton();
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
    updateVoiceButton();

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


function noticeContent(type, language) {
    const isArabic = language === "ar";
    if (type === "contact") {
        return {
            title: translations[language].contactNoticeTitle,
            paragraphs: isArabic
                ? [
                      "يستخدم هذا الشات بوت وسائل التخزين الضرورية في المتصفح فقط لتشغيل تجربة المحادثة.",
                      "يستخدم localStorage للاحتفاظ بمعرّف جلسة المحادثة ومعرّف ربط العميل بالجلسة، كما يستخدم sessionStorage للاحتفاظ بسجل المحادثة الظاهر وسجل الأدلة خلال جلسة المتصفح.",
                      "تستخدم لوحة طلبات الاتصال الداخلية لفريق المبيعات ملف تعريف ارتباط ضروريًا وموقّعًا لتسجيل دخول الموظفين، مع حماية CSRF، وبخصائص HttpOnly وSameSite=Lax.",
                      "لا يستخدم هذا الشات بوت ملفات تعريف ارتباط إعلانية أو ملفات تحليل اختيارية.",
                      "يجمع هذا الشات بوت الاسم ورقم الهاتف المحمول ومعرّف جلسة المحادثة الذي تقدمه. وإذا طلبت مكالمة من فريق المبيعات، فسيتم أيضًا تخزين حالة طلب المكالمة ووقت الطلب وحالة التواصل.",
                      "تُستخدم هذه المعلومات لإدارة جلسة المحادثة، وربط طلبات الاتصال بالبيانات التي قدمتها، وتمكين موظفي جورمول المخولين من متابعة طلبات الاتصال من فريق المبيعات.",
                      "تُخزن البيانات في قاعدة بيانات PostgreSQL الخاصة بهذا التشغيل. ولا يتم إرسال الاسم أو رقم الهاتف المحمول أو حالة الإشعارات أو سجلات طلبات الاتصال إلى OpenAI باعتبارها أسئلة معرفية.",
                      "قد يتم إرسال نص السؤال والسياق الضروري للمحادثة فقط لإنشاء إجابة الشات بوت. ويجب اعتماد مدة الاحتفاظ بالبيانات قبل التشغيل الإنتاجي.",
                      "للاستفسار عن بياناتك، تواصل مع جورمول عبر البريد الإلكتروني info@jormall.com أو الرقم +962 77 99 37272."
                  ]
                : [
                      "This chatbot uses necessary browser storage only to operate the experience.",
                      "It uses localStorage to keep the chat session identifier and lead-session identifier, and sessionStorage to keep visible conversation history and evidence history during the browser session.",
                      "The internal sales callback dashboard uses a necessary signed login cookie with CSRF protection for employees, using HttpOnly and SameSite=Lax.",
                      "This chatbot does not use advertising cookies or optional analytics cookies.",
                      "This chatbot collects the name, mobile number, and chatbot session identifier you provide. If you request a sales callback, the callback status, request time, and contacted status are also stored.",
                      "This information is used to manage the chatbot session, connect callback requests to the details you provided, and allow authorized JorMall staff to follow up on sales callback requests.",
                      "The data is stored in this deployment's PostgreSQL database. Name, mobile number, notice status, and callback records are not sent to OpenAI as knowledge questions.",
                      "Only the question text and necessary conversation context may be sent to generate a chatbot answer. Data retention should be confirmed before production.",
                      "For questions about your information, contact JorMall at info@jormall.com or +962 77 99 37272."
                  ]
        };
    }

    if (type === "privacy") {
        return {
            title: translations[language].privacyNoticeTitle,
            paragraphs: isArabic
                ? [
                      "يجمع هذا الشات بوت الاسم ورقم الهاتف المحمول ومعرّف جلسة المحادثة. وعند طلب اتصال من فريق المبيعات، يتم حفظ حالة الطلب ووقت الطلب وحالة التواصل.",
                      "تستخدم هذه المعلومات لإدارة جلسة المحادثة، وربط طلب الاتصال بالبيانات التي قدمتها، وتمكين موظفي جورمول المخولين من متابعة طلبات الاتصال.",
                      "يتم تخزين البيانات في قاعدة بيانات PostgreSQL الخاصة بهذا النشر. لا يتم إرسال الاسم أو رقم الهاتف أو حالة الإشعار أو طلبات الاتصال إلى OpenAI ضمن أسئلة المعرفة.",
                      "قد يتم إرسال نص السؤال ومعلومات المحادثة اللازمة فقط لتوليد إجابة الشات بوت. يجب تأكيد مدة الاحتفاظ بالبيانات قبل التشغيل الإنتاجي.",
                      "للاستفسار عن معلوماتك، تواصل مع جورمول عبر info@jormall.com أو +962 77 99 37272."
                  ]
                : [
                      "This chatbot collects the name, mobile number, and chatbot session identifier you provide. If you request a sales callback, the callback status, request time, and contacted status are also stored.",
                      "This information is used to manage the chatbot session, connect callback requests to the details you provided, and allow authorized JorMall staff to follow up on sales callback requests.",
                      "The data is stored in this deployment's PostgreSQL database. Name, mobile number, notice status, and callback records are not sent to OpenAI as knowledge questions.",
                      "Only the question text and necessary conversation context may be sent to generate a chatbot answer. Data retention should be confirmed before production.",
                      "For questions about your information, contact JorMall at info@jormall.com or +962 77 99 37272."
                  ]
        };
    }

    return {
        title: translations[language].cookieNoticeTitle,
        paragraphs: isArabic
            ? [
                  "يستخدم هذا الشات بوت وسائل تخزين ضرورية في المتصفح فقط لتشغيل التجربة.",
                  "يستخدم localStorage لحفظ معرّف جلسة المحادثة ومعرّف جلسة بيانات التواصل، ويستخدم sessionStorage لحفظ سجل المحادثة الظاهر وسجل الأدلة خلال الجلسة.",
                  "تستخدم لوحة طلبات الاتصال الداخلية ملف تعريف ارتباط موقّع وضروري لتسجيل دخول الموظفين وحماية CSRF، مع HttpOnly و SameSite=Lax.",
                  "لا يستخدم هذا الشات بوت ملفات تعريف ارتباط للإعلانات أو التحليلات الاختيارية."
              ]
            : [
                  "This chatbot uses necessary browser storage only to operate the experience.",
                  "It uses localStorage to keep the chat session identifier and lead-session identifier, and sessionStorage to keep visible conversation history and evidence history during the browser session.",
                  "The internal sales callback dashboard uses a necessary signed login cookie with CSRF protection for employees, using HttpOnly and SameSite=Lax.",
                  "This chatbot does not use advertising cookies or optional analytics cookies."
              ]
    };
}


function focusableDialogElements() {
    return Array.from(
        noticeDialog?.querySelectorAll(
            "button:not(:disabled), [href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex='-1'])"
        ) || []
    );
}


function openNoticeDialog(type, opener) {
    if (!noticeDialogBackdrop || !noticeDialog || !noticeDialogTitle || !noticeDialogBody) {
        return;
    }

    const content = noticeContent(type, currentLanguage);
    noticeReturnFocus = opener || document.activeElement;
    if (type === "cookie") {
        cookieNoticeOpened = true;
    } else if (type === "privacy") {
        privacyNoticeOpened = true;
    }

    noticeDialogTitle.textContent = content.title;
    noticeDialogBody.innerHTML = "";
    for (const paragraphText of content.paragraphs) {
        const paragraph = document.createElement("p");
        paragraph.textContent = paragraphText;
        noticeDialogBody.appendChild(paragraph);
    }
    noticeDialog.dir = currentLanguage === "ar" ? "rtl" : "ltr";
    noticeDialogBackdrop.hidden = false;
    document.documentElement.classList.add("notice-dialog-open");
    noticeDialogClose?.focus();
}


function closeNoticeDialog() {
    if (!noticeDialogBackdrop) {
        return;
    }
    noticeDialogBackdrop.hidden = true;
    document.documentElement.classList.remove("notice-dialog-open");
    if (noticeReturnFocus && typeof noticeReturnFocus.focus === "function") {
        noticeReturnFocus.focus();
    }
    noticeReturnFocus = null;
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
                chat_session_id: sessionId,
                name: normalizeLeadName(leadNameInput.value),
                phone: normalizeLeadPhone(leadPhoneInput.value),
                cookie_notice_opened: cookieNoticeOpened,
                privacy_notice_opened: privacyNoticeOpened
            })
        });

        if (!response.ok) {
            const payload = await response.json().catch(() => ({}));
            throw new Error(payload.detail || translations[currentLanguage].leadSubmitError);
        }

        const payload = await response.json().catch(() => ({}));
        conversationId = String(payload.conversation_id || "");
        if (conversationId) {
            localStorage.setItem(CONVERSATION_ID_STORAGE_KEY, conversationId);
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

    const image = document.createElement("img");
    image.alt = mediaItem.label;
    image.loading = "eager";

    image.style.maxWidth = "100%";
    image.style.borderRadius = "14px";
    image.style.display = "block";
    image.style.marginTop = "10px";
    image.style.boxShadow = "0 10px 28px rgba(0, 0, 0, 0.18)";

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
    };

    image.onerror = () => {
        if (
            !fallbackAttempted &&
            mediaItem.fallback_url &&
            appUrl(mediaItem.fallback_url) !== image.src
        ) {
            fallbackAttempted = true;
            image.src = appUrl(mediaItem.fallback_url);
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

    const caption = document.createElement("figcaption");
    caption.textContent = mediaItem.label;
    caption.style.fontSize = "0.85rem";
    caption.style.opacity = "0.75";
    caption.style.marginTop = "8px";

    figure.appendChild(loadingStatus);
    figure.appendChild(image);
    figure.appendChild(caption);

    image.src = appUrl(mediaItem.url);

    return figure;
}


function createVideoMediaCard(mediaItem) {
    const figure = document.createElement("figure");
    figure.className = "media-card media-card-video";

    const video = document.createElement("video");
    video.controls = true;
    video.preload = "metadata";
    video.src = appUrl(mediaItem.url);

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
    button.disabled = hasPendingSalesCallback;
    button.setAttribute("aria-disabled", String(hasPendingSalesCallback));
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
        scrollToLatestMessage();
        return false;
    }

    const article = document.createElement("article");
    article.className = "message assistant-message callback-confirmation-message";
    article.dir = currentLanguage === "ar" ? "rtl" : "ltr";

    const bubble = document.createElement("div");
    bubble.className = "message-bubble callback-confirmation";

    const title = document.createElement("strong");
    title.className = "callback-confirmation-title";
    title.textContent = translations[currentLanguage].callbackTitle;

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
    bubble.appendChild(title);
    bubble.appendChild(prompt);
    bubble.appendChild(actions);
    article.appendChild(bubble);
    chatMessages.appendChild(article);
    scrollToLatestMessage();

    cancelButton.addEventListener("click", () => {
        article.remove();
        onCancel?.();
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
    if (!chatbotConfig.salesCallbackEndpoint || confirmButton.disabled) {
        return;
    }

    confirmButton.disabled = true;
    cancelButton.disabled = true;
    confirmButton.textContent = translations[currentLanguage].callbackSubmitting;

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
        hasPendingSalesCallback = true;
        appendMessage("assistant", payload.message || "");
    } catch (error) {
        confirmButton.disabled = false;
        cancelButton.disabled = false;
        confirmButton.textContent = translations[currentLanguage].callbackConfirm;
        appendMessage(
            "assistant",
            error.message || translations[currentLanguage].callbackError,
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
    applyMessageLanguage(bubble, cleanedText);

    const paragraph = document.createElement("p");
    if (role === "assistant") {
        renderAssistantText(paragraph, cleanedText);
    } else {
        paragraph.textContent = cleanedText;
    }

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
        renderAssistantText(
            welcomeMessage,
            translations[currentLanguage].welcome
        );
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

    stopBrowserSpeech();

    conversationMemory = [];
    sessionId = createSessionId();
    conversationId = "";

    try {
        localStorage.setItem(SESSION_ID_STORAGE_KEY, sessionId);
        localStorage.removeItem(CONVERSATION_ID_STORAGE_KEY);
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
    applyMessageLanguage(bubble, initialStatus);

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

    renderAssistantText(state.paragraph, visibleText);

    state.article.dir = containsArabic(visibleText) ? "rtl" : "ltr";
    applyMessageLanguage(state.bubble, visibleText);

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
    renderAssistantText(state.paragraph, parsed.text);

    state.article.dir = containsArabic(parsed.text)
        ? "rtl"
        : "ltr";
    applyMessageLanguage(state.bubble, parsed.text);

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


function handleStreamingFailure(state) {
    const fallback = translations[currentLanguage].partialFallback;
    const currentText = cleanMemoryContent(state.paragraph.textContent);

    if (state.hasText && currentText) {
        if (!currentText.includes(fallback)) {
            appendStreamingDelta(state, `\n\n${fallback}`);
        }
        return;
    }

    replaceStreamingMessage(
        state,
        translations[currentLanguage].serviceError,
        false
    );
}


function finishStreamingMessage(state) {
    state.cursor.remove();
    state.article.classList.remove("streaming-message");

    const parsed = parseAssistantContent(
        state.paragraph.textContent,
        state.mediaItems
    );

    renderAssistantText(state.paragraph, parsed.text);
    state.article.dir = containsArabic(parsed.text) ? "rtl" : "ltr";
    applyMessageLanguage(state.bubble, parsed.text);

    removeVisibleSources(state.article);
    removeFollowUpBlocks(state.article);

    if (parsed.media.length) {
        renderMediaItems(state, parsed.media);
    }

    if (state.messageId) {
        const play = document.createElement("button");
        play.type = "button";
        play.className = "assistant-speech-play";
        play.textContent = currentLanguage === "ar" ? "تشغيل / إعادة" : "Play / replay";
        play.dataset.messageId = state.messageId;
        play.addEventListener("click", () => {
            primeVoicePlayback();
            if (chatbotConfig.voiceTransport === "openai_webrtc") {
                void window.JorMallWebRTC.replaySavedAnswer(
                    state.paragraph.textContent,
                    state.messageId,
                    state.savedSessionId
                );
            } else {
                void speakAssistantAnswer(state.paragraph.textContent, currentLanguage,
                    state.messageId, state.savedSessionId);
            }
        });
        state.bubble.appendChild(play);
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
        button.dataset.actionId = item.id || "";
        button.dataset.starterType = item.type || "question";
        button.dir = currentLanguage === "ar" ? "rtl" : "ltr";

        if (isSalesCallbackStarterItem(item)) {
            const icon = document.createElement("i");
            icon.className = "fa-solid fa-phone starter-phone-icon";
            icon.setAttribute("aria-hidden", "true");

            const label = document.createElement("span");
            label.textContent = item.label;

            button.classList.add("has-starter-phone-icon");
            button.append(icon, label);
        } else {
            button.textContent = item.label;
        }

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

    submitQuestion(item.label, {
        fromStarter: true,
        starterActionId: item.id || ""
    });
}


function updateLanguage(language, options = {}) {
    if (language !== currentLanguage) {
        if (!options.preserveVoiceReply) {
            cancelPendingVoiceReply = true;
            stopBrowserSpeech();
            if (voiceState === "recording") {
                cancelCurrentRecording = true;
                stopVoiceRecording();
            }
        }
    }
    currentLanguage = language;

    document.documentElement.lang = language;
    document.documentElement.dir =
        language === "ar" ? "rtl" : "ltr";
    document.title = translations[language].pageTitle;

    document.querySelectorAll("[data-i18n]").forEach((element) => {
        const key = element.dataset.i18n;

        if (translations[language][key]) {
            element.textContent = translations[language][key];
        }
    });

    document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
        const key = element.dataset.i18nAriaLabel;

        if (translations[language][key]) {
            element.setAttribute("aria-label", translations[language][key]);
        }
    });

    document.querySelectorAll("[data-i18n-title]").forEach((element) => {
        const key = element.dataset.i18nTitle;

        if (translations[language][key]) {
            element.setAttribute("title", translations[language][key]);
        }
    });

    document.querySelectorAll("[data-i18n-alt]").forEach((element) => {
        const key = element.dataset.i18nAlt;

        if (translations[language][key]) {
            element.setAttribute("alt", translations[language][key]);
        }
    });

    if (welcomeMessage?.isConnected) {
        renderAssistantText(
            welcomeMessage,
            translations[language].welcome
        );

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
    updateVoiceButton();
    validateLeadForm({
        showErrors: Boolean(
            leadNameError?.textContent ||
            leadPhoneError?.textContent
        ),
    });
}


function handleStreamEvent(event, state) {
    if (event.type === "saved") {
        state.messageId = event.message_id;
        state.savedSessionId = sessionId;
        return;
    }
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
        handleStreamingFailure(state);
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

    if (options.voiceReply) {
        markVoiceTiming("chat_started");
    }

    const detectedQuestionLanguage = detectTextLanguage(message, currentLanguage);
    if (detectedQuestionLanguage !== currentLanguage) {
        updateLanguage(detectedQuestionLanguage, {
            preserveVoiceReply: Boolean(options.voiceReply)
        });
    }

    stopBrowserSpeech();

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
            chatbotConfig.streamEndpoint ||
                appUrl(`/api/chat/${encodeURIComponent(chatbotConfig.clientSlug)}/stream`),
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
                input_mode: options.voiceReply ? "voice" : "text",
                history: backendHistoryBeforeRequest,
                evidence_history: getEvidenceHistoryForRequest()
            })
            }
        );

        if (!response.ok) {
            await response.text().catch(() => "");
            throw new Error("stream_failed");
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
        if (options.voiceReply) {
            markVoiceTiming("voice_failed", { stage: "chat" });
        }
        handleStreamingFailure(streamState);
    } finally {
        finishStreamingMessage(streamState);

        if (options.voiceReply) {
            markVoiceTiming("chat_completed", {
                saved: Boolean(streamState.messageId)
            });
        }

        const finalAssistantAnswer = cleanMemoryContent(
            streamState.paragraph.textContent
        );

        if (finalAssistantAnswer) {
            const detectedAnswerLanguage = detectTextLanguage(
                finalAssistantAnswer,
                currentLanguage
            );
            if (detectedAnswerLanguage !== currentLanguage) {
                updateLanguage(detectedAnswerLanguage, {
                    preserveVoiceReply: true
                });
            }
            rememberTurn("assistant", finalAssistantAnswer);
            if (options.voiceReply && !cancelPendingVoiceReply) {
                if (chatbotConfig.voiceTransport === "openai_webrtc") {
                    await window.JorMallWebRTC.deliverSavedAnswer({
                        answer: finalAssistantAnswer,
                        messageId: streamState.messageId,
                        savedSessionId: streamState.savedSessionId,
                        delegationId: options.webRtcDelegationId || ""
                    });
                } else {
                    speakAssistantAnswer(
                        finalAssistantAnswer,
                        currentLanguage,
                        streamState.messageId,
                        streamState.savedSessionId
                    );
                }
            } else if (options.voiceReply) {
                hideVoiceExperience();
            }
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


document.querySelectorAll("[data-notice-dialog]").forEach((button) => {
    button.addEventListener("click", () => {
        openNoticeDialog(button.dataset.noticeDialog, button);
    });
});


if (noticeDialogClose) {
    noticeDialogClose.addEventListener("click", closeNoticeDialog);
}


if (noticeDialogBackdrop) {
    noticeDialogBackdrop.addEventListener("mousedown", (event) => {
        if (event.target === noticeDialogBackdrop) {
            closeNoticeDialog();
        }
    });

    noticeDialogBackdrop.addEventListener("keydown", (event) => {
        if (noticeDialogBackdrop.hidden) {
            return;
        }

        if (event.key === "Escape") {
            event.preventDefault();
            closeNoticeDialog();
            return;
        }

        if (event.key !== "Tab") {
            return;
        }

        const focusable = focusableDialogElements();
        if (!focusable.length) {
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


if (voiceButton) {
    voiceButton.addEventListener("click", () => {
        primeVoicePlayback();
        if (voiceState === "recording") {
            stopVoiceRecording();
        } else {
            startVoiceRecording();
        }
    });
}


function cancelVoiceExperience() {
    cancelPendingVoiceReply = true;
    if (voiceState === "recording") {
        cancelCurrentRecording = true;
        stopVoiceRecording();
    } else {
        stopBrowserSpeech();
        hideVoiceExperience();
    }
    setVoiceStatus("");
}


if (voiceOrbButton) {
    voiceOrbButton.addEventListener("click", () => {
        primeVoicePlayback();
        if (voiceState === "recording") {
            stopVoiceRecording();
        } else {
            cancelVoiceExperience();
        }
    });
}


if (voiceExperienceClose) {
    voiceExperienceClose.addEventListener("click", cancelVoiceExperience);
}


document.querySelectorAll(".language-button").forEach((button) => {
    button.addEventListener("click", () => {
        updateLanguage(button.dataset.language);
    });
});


document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && voiceExperience && !voiceExperience.hidden) {
        event.preventDefault();
        event.stopImmediatePropagation();
        cancelVoiceExperience();
    }
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
if (chatbotConfig.voiceEnabled && !window.isSecureContext) {
    setVoiceStatus(translations[currentLanguage].voiceSecureContext);
} else if (chatbotConfig.voiceEnabled && !browserVoiceInputSupported()) {
    setVoiceStatus(translations[currentLanguage].voiceError);
}
updateVoiceButton();
notifyEmbedParent("ready");
