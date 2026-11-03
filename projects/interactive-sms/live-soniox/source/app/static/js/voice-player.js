/* Saved-message playback. Shared UI hooks are provided by chat.js. */
const speechVoiceCache = { ar: null, en: null };
let speechRequestSerial = 0;
let voiceAudioContext = null;
let voicePlaybackEndTime = 0;
let activeVoiceAbortController = null;
let voiceAudioElement = null;
let voiceAudioObjectUrl = "";
const activeVoiceSources = new Set();


window.JorMallVoiceTimings = (() => {
    let sequence = 0;
    let current = null;
    const history = [];

    function duration(startName, endName) {
        const start = current?.marks?.[startName]?.elapsedMs;
        const end = current?.marks?.[endName]?.elapsedMs;
        return Number.isFinite(start) && Number.isFinite(end)
            ? Math.round((end - start) * 10) / 10
            : null;
    }

    function updateMetrics() {
        if (!current) return;
        current.metrics = {
            recordingMs: duration("recording_started", "recording_completed"),
            transcriptionMs: duration("transcription_started", "transcription_completed"),
            chatMs: duration("chat_started", "chat_completed"),
            ttsFirstAudioMs: duration("tts_requested", "tts_first_audio_byte"),
            playbackStartMs: duration("tts_requested", "playback_started")
        };
    }

    function start(language) {
        current = {
            id: `voice-${Date.now()}-${++sequence}`,
            language,
            startedAt: performance.now(),
            marks: {}
        };
        mark("recording_started");
        return current.id;
    }

    function mark(name, detail = {}) {
        if (!current) {
            current = {
                id: `voice-${Date.now()}-${++sequence}`,
                language: document.documentElement.lang || "en",
                startedAt: performance.now(),
                marks: {}
            };
        }
        const now = performance.now();
        current.marks[name] = {
            elapsedMs: Math.round((now - current.startedAt) * 10) / 10,
            ...detail
        };
        updateMetrics();
        window.dispatchEvent(new CustomEvent("jormall:voice-timing", {
            detail: { id: current.id, name, ...current.marks[name] }
        }));
    }

    function finish(detail = {}) {
        if (!current) return;
        mark("completed", detail);
        history.push(JSON.parse(JSON.stringify(current)));
        if (history.length > 20) history.shift();
        current = null;
    }

    function snapshot() {
        return JSON.parse(JSON.stringify({ current, history }));
    }

    return { start, mark, finish, snapshot };
})();


function markVoiceTiming(name, detail = {}) {
    window.JorMallVoiceTimings?.mark(name, detail);
}


function createVoiceAudioContext() {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return null;
    return new AudioContextClass({ latencyHint: "interactive" });
}


function primeVoicePlayback() {
    // Safari needs playback unlocked directly inside the user's click.
    try {
        if (!voiceAudioContext || voiceAudioContext.state === "closed") {
            voiceAudioContext = createVoiceAudioContext();
        }
        if (voiceAudioContext) {
            const silentBuffer = voiceAudioContext.createBuffer(1, 1, 24000);
            const silentSource = voiceAudioContext.createBufferSource();
            silentSource.buffer = silentBuffer;
            silentSource.connect(voiceAudioContext.destination);
            silentSource.start();
            if (voiceAudioContext.state !== "running") {
                void voiceAudioContext.resume().catch(() => {});
            }
        }
    } catch {
        voiceAudioContext = null;
    }

    try {
        if (!voiceAudioElement) {
            voiceAudioElement = new Audio();
            voiceAudioElement.preload = "auto";
            voiceAudioElement.playsInline = true;
        }
        voiceAudioElement.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";
        const playAttempt = voiceAudioElement.play();
        if (playAttempt?.then) {
            void playAttempt.then(() => voiceAudioElement.pause()).catch(() => {});
        }
    } catch {
        // Web Audio remains the primary path.
    }
}


async function ensureVoiceAudioContext() {
    if (!voiceAudioContext || voiceAudioContext.state === "closed") {
        voiceAudioContext = createVoiceAudioContext();
    }
    if (!voiceAudioContext) return null;
    if (voiceAudioContext.state !== "running") {
        await voiceAudioContext.resume();
    }
    return voiceAudioContext.state === "running" ? voiceAudioContext : null;
}


function stopBrowserSpeech() {
    speechRequestSerial += 1;
    window.speechSynthesis?.cancel();
    activeVoiceAbortController?.abort();
    activeVoiceAbortController = null;
    activeVoiceSources.forEach((source) => {
        try { source.stop(); } catch { /* source may already be stopped */ }
    });
    activeVoiceSources.clear();
    voicePlaybackEndTime = voiceAudioContext?.currentTime || 0;
    if (voiceAudioElement) {
        voiceAudioElement.pause();
        voiceAudioElement.removeAttribute("src");
    }
    if (voiceAudioObjectUrl) {
        URL.revokeObjectURL(voiceAudioObjectUrl);
        voiceAudioObjectUrl = "";
    }
    hideVoiceExperience();
    window.JorMallWebRTC?.interruptPlayback();
}


function pcmBufferFromBytes(context, bytes) {
    const sampleCount = Math.floor(bytes.byteLength / 2);
    const buffer = context.createBuffer(1, sampleCount, 24000);
    const channel = buffer.getChannelData(0);
    const view = new DataView(bytes.buffer, bytes.byteOffset, sampleCount * 2);
    for (let index = 0; index < sampleCount; index += 1) {
        channel[index] = view.getInt16(index * 2, true) / 32768;
    }
    return buffer;
}


function wavBlobFromPcmBytes(bytes) {
    const wav = new ArrayBuffer(44 + bytes.byteLength);
    const view = new DataView(wav);
    const writeText = (offset, value) => {
        for (let index = 0; index < value.length; index += 1) {
            view.setUint8(offset + index, value.charCodeAt(index));
        }
    };
    writeText(0, "RIFF");
    view.setUint32(4, 36 + bytes.byteLength, true);
    writeText(8, "WAVE");
    writeText(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, 24000, true);
    view.setUint32(28, 48000, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeText(36, "data");
    view.setUint32(40, bytes.byteLength, true);
    new Uint8Array(wav, 44).set(bytes);
    return new Blob([wav], { type: "audio/wav" });
}


async function playPcmWithNativeAudio(response, requestSerial) {
    const bytes = new Uint8Array(await response.arrayBuffer());
    markVoiceTiming("tts_first_audio_byte", { bufferedFallback: true });
    if (!bytes.length || requestSerial !== speechRequestSerial) {
        throw new Error("empty_audio_response");
    }
    if (!voiceAudioElement) {
        voiceAudioElement = new Audio();
        voiceAudioElement.playsInline = true;
    }
    if (voiceAudioObjectUrl) URL.revokeObjectURL(voiceAudioObjectUrl);
    voiceAudioObjectUrl = URL.createObjectURL(wavBlobFromPcmBytes(bytes));
    voiceAudioElement.src = voiceAudioObjectUrl;
    voiceAudioElement.onplay = () => {
        markVoiceTiming("playback_started", { bufferedFallback: true });
        setVoiceExperienceState("speaking");
    };
    voiceAudioElement.onended = () => {
        window.JorMallVoiceTimings?.finish({ outcome: "played" });
        hideVoiceExperience();
    };
    await voiceAudioElement.play();
}


async function playEncodedAudio(response, requestSerial) {
    const audioBlob = await response.blob();
    if (!audioBlob.size || requestSerial !== speechRequestSerial) {
        throw new Error("empty_audio_response");
    }
    if (!voiceAudioElement) {
        voiceAudioElement = new Audio();
        voiceAudioElement.playsInline = true;
    }
    if (voiceAudioObjectUrl) URL.revokeObjectURL(voiceAudioObjectUrl);
    voiceAudioObjectUrl = URL.createObjectURL(audioBlob);
    voiceAudioElement.src = voiceAudioObjectUrl;
    voiceAudioElement.onplay = () => setVoiceExperienceState("speaking");
    voiceAudioElement.onended = hideVoiceExperience;
    await voiceAudioElement.play();
}


async function playStreamingPcm(response, requestSerial) {
    const context = await ensureVoiceAudioContext();
    if (!context || !response.body?.getReader) {
        await playPcmWithNativeAudio(response, requestSerial);
        return;
    }

    const reader = response.body.getReader();
    let carry = new Uint8Array(0);
    let firstAudioChunk = true;
    let scheduledChunks = 0;

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        if (requestSerial !== speechRequestSerial) {
            await reader.cancel();
            return;
        }

        const incoming = value || new Uint8Array(0);
        if (firstAudioChunk) {
            markVoiceTiming("tts_first_audio_byte", { bufferedFallback: false });
        }
        const combined = new Uint8Array(carry.length + incoming.length);
        combined.set(carry);
        combined.set(incoming, carry.length);
        const usableLength = combined.length - (combined.length % 2);
        if (!usableLength) {
            carry = combined;
            continue;
        }

        const audioBytes = combined.subarray(0, usableLength);
        carry = combined.subarray(usableLength);
        const audioBuffer = pcmBufferFromBytes(context, audioBytes);
        const source = context.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(context.destination);
        const safetyLead = firstAudioChunk ? 0.055 : 0.012;
        const startAt = Math.max(
            voicePlaybackEndTime,
            context.currentTime + safetyLead
        );
        source.start(startAt);
        scheduledChunks += 1;
        voicePlaybackEndTime = startAt + audioBuffer.duration;
        activeVoiceSources.add(source);
        source.addEventListener("ended", () => activeVoiceSources.delete(source), { once: true });

        if (firstAudioChunk) {
            firstAudioChunk = false;
            markVoiceTiming("playback_started", {
                scheduledDelayMs: Math.round(Math.max(0, startAt - context.currentTime) * 1000)
            });
            setVoiceExperienceState("speaking");
        }
    }

    if (!scheduledChunks) {
        throw new Error("empty_audio_response");
    }

    const remainingMs = Math.max(
        0,
        ((voicePlaybackEndTime - context.currentTime) * 1000) + 180
    );
    window.setTimeout(() => {
        if (requestSerial === speechRequestSerial) {
            window.JorMallVoiceTimings?.finish({ outcome: "played" });
            hideVoiceExperience();
        }
    }, remainingMs);
}


function speechVoiceScore(voice, language) {
    const name = String(voice.name || "").toLowerCase();
    const locale = String(voice.lang || "").toLowerCase();
    const exactLocale = language === "ar" ? "ar-JO" : "en-US";
    const languagePrefix = language === "ar" ? "ar" : "en";
    const preferredNames = language === "ar"
        ? ["majed", "maged", "tarik", "tariq", "zeina", "hoda"]
        : ["samantha", "ava", "allison", "karen"];
    const nameIndex = preferredNames.findIndex((item) => name.includes(item));
    let score = 0;
    if (nameIndex >= 0) score += 100 - nameIndex;
    if (locale === exactLocale.toLowerCase()) score += 50;
    if (locale.startsWith(`${languagePrefix}-`)) score += 30;
    if (locale.startsWith(languagePrefix)) score += 20;
    if (voice.localService) score += 10;
    return score;
}


async function availableSpeechVoices() {
    let voices = window.speechSynthesis?.getVoices?.() || [];
    if (voices.length || !window.speechSynthesis?.addEventListener) {
        return voices;
    }
    await new Promise((resolve) => {
        const timeout = window.setTimeout(resolve, 800);
        window.speechSynthesis.addEventListener("voiceschanged", () => {
            window.clearTimeout(timeout);
            resolve();
        }, { once: true });
    });
    voices = window.speechSynthesis?.getVoices?.() || [];
    return voices;
}


async function preferredSpeechVoice(language) {
    if (speechVoiceCache[language]) {
        return speechVoiceCache[language];
    }
    const languagePrefix = language === "ar" ? "ar" : "en";
    const voices = (await availableSpeechVoices())
        .filter((voice) => String(voice.lang || "").toLowerCase().startsWith(languagePrefix))
        .sort((left, right) =>
            speechVoiceScore(right, language) - speechVoiceScore(left, language) ||
            String(left.name || "").localeCompare(String(right.name || ""))
        );
    speechVoiceCache[language] = voices[0] || null;
    return speechVoiceCache[language];
}

async function speakAssistantAnswer(text, language, messageId, savedSessionId = sessionId) {
    const cleanText = cleanVisibleAssistantText(text);
    if (!cleanText) {
        return;
    }

    stopBrowserSpeech();
    if (!messageId) {
        setVoiceStatus(language === "ar" ? "لم يتم حفظ الرد الصوتي بعد. يمكنك قراءة الإجابة." : "This answer is not ready for speech. You can read the written answer.");
        hideVoiceExperience(); return;
    }
    setVoiceStatus("");
    let requestSerial = speechRequestSerial;
    setVoiceExperienceState("preparing");
    markVoiceTiming("tts_requested");
    try {
        activeVoiceAbortController = new AbortController();
        const response = await fetch(chatbotConfig.voiceSpeechEndpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            signal: activeVoiceAbortController.signal,
            body: JSON.stringify({
                language: "auto",
                session_id: savedSessionId,
                message_id: messageId,
                lead_session_id: leadSessionId || ""
            })
        });
        if (!response.ok) {
            throw new Error("speech_generation_failed");
        }
        markVoiceTiming("tts_headers", {
            provider: response.headers.get("x-voice-provider") || "",
            model: response.headers.get("x-voice-model") || "",
            voice: response.headers.get("x-voice-voice") || "",
            cache: response.headers.get("x-voice-cache") || "",
            serverFirstAudioMs: Number(response.headers.get("x-voice-first-audio-ms") || 0),
            sourceCharacters: Number(response.headers.get("x-voice-source-characters") || 0),
            speechCharacters: Number(response.headers.get("x-voice-speech-characters") || 0),
            compacted: response.headers.get("x-voice-compacted") === "true",
            detectedLanguage: response.headers.get("x-voice-language") || ""
        });
        if (!String(response.headers.get("content-type")).includes("application/x-jormall-pcm") ||
            response.headers.get("x-assistant-message-id") !== messageId ||
            response.headers.get("x-voice-provider") !== chatbotConfig.voiceTtsProvider) throw new Error("voice_contract_mismatch");
        await playStreamingPcm(JorMallVoiceProtocol.pcmResponse(response), requestSerial);
        activeVoiceAbortController = null;
        return;
    } catch (error) {
        if (error?.name === "AbortError" || requestSerial !== speechRequestSerial) return;
        markVoiceTiming("voice_failed", { stage: "speech" });
        stopBrowserSpeech();
        setVoiceStatus(language === "ar" ? "تعذر تشغيل الصوت. يمكنك قراءة الإجابة المكتوبة." : "Voice playback failed. You can read the written answer.");
        hideVoiceExperience();
        if (!chatbotConfig.voiceBrowserFallbackEnabled) return;
        requestSerial = speechRequestSerial;
        setVoiceStatus(language === "ar" ? "يتم استخدام صوت المتصفح البديل." : "Using the explicitly enabled browser fallback voice.");
    }

    if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) {
        hideVoiceExperience();
        return;
    }
    const voice = await preferredSpeechVoice(language);
    if (requestSerial !== speechRequestSerial) return;
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = language === "ar" ? "ar-JO" : "en-US";
    utterance.rate = language === "ar" ? 1.02 : 1.0;
    if (voice) utterance.voice = voice;
    utterance.addEventListener("start", () => setVoiceExperienceState("speaking"), { once: true });
    utterance.addEventListener("end", hideVoiceExperience, { once: true });
    utterance.addEventListener("error", hideVoiceExperience, { once: true });
    window.speechSynthesis.cancel();
    window.speechSynthesis.resume();
    setVoiceExperienceState("speaking");
    window.speechSynthesis.speak(utterance);
}
