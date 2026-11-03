/* Temporary true-live PCM capture for ports 5005-5007 of the removable matrix. */
let liveVoiceSocket = null;
let liveCaptureContext = null;
let liveCaptureSource = null;
let liveCaptureProcessor = null;
let liveSilentGain = null;
let liveFinalReceived = false;

function stopVoiceTracks() {
    try { liveCaptureProcessor?.disconnect(); } catch {}
    try { liveCaptureSource?.disconnect(); } catch {}
    try { liveSilentGain?.disconnect(); } catch {}
    liveCaptureProcessor = null;
    liveCaptureSource = null;
    liveSilentGain = null;
    if (liveCaptureContext && liveCaptureContext.state !== "closed") {
        void liveCaptureContext.close().catch(() => {});
    }
    liveCaptureContext = null;
    voiceStream?.getTracks().forEach((track) => track.stop());
    voiceStream = null;
    mediaRecorder = null;
}

function liveSocketUrl(path) {
    const url = new URL(path, window.location.href);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return url.toString();
}

function pcm16At24k(input, inputRate) {
    const ratio = inputRate / 24000;
    const length = Math.max(1, Math.floor(input.length / ratio));
    const output = new Int16Array(length);
    for (let i = 0; i < length; i += 1) {
        const position = i * ratio;
        const left = Math.floor(position);
        const fraction = position - left;
        const a = input[left] || 0;
        const b = input[Math.min(left + 1, input.length - 1)] || a;
        const sample = Math.max(-1, Math.min(1, a + (b - a) * fraction));
        output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    return output.buffer;
}

function cleanupLiveSocket(sendCancel = false) {
    if (liveVoiceSocket) {
        if (sendCancel && liveVoiceSocket.readyState === WebSocket.OPEN) {
            liveVoiceSocket.send(JSON.stringify({ type: "cancel" }));
        }
        try { liveVoiceSocket.close(); } catch {}
    }
    liveVoiceSocket = null;
    stopVoiceTracks();
}

async function acceptLiveTranscript(payload) {
    const transcript = String(payload.transcript || "").trim();
    if (!transcript) throw new Error("empty_transcript");
    liveFinalReceived = true;
    cleanupLiveSocket(false);
    const voiceLanguage = payload.language === "ar" ? "ar" : "en";
    if (voiceLanguage !== currentLanguage) {
        updateLanguage(voiceLanguage, { preserveVoiceReply: true });
    }
    markVoiceTiming("transcription_completed", {
        detectedLanguage: voiceLanguage,
        provider: payload.provider || "",
        model: payload.model || "",
        audioDurationMs: Number(payload.audio_duration_ms || 0)
    });
    setVoiceExperienceState("thinking");
    chatInput.value = transcript;
    resizeInput();
    await sendMessage(transcript, { voiceReply: true, voiceLanguage });
    setVoiceStatus("");
    voiceState = "idle";
    setVoiceComposerLocked(false);
    updateVoiceButton();
}

function handleLiveMessage(event) {
    let payload;
    try { payload = JSON.parse(event.data); } catch { return; }
    if (payload.type === "ready") {
        markVoiceTiming("transcription_headers", {
            provider: payload.provider || "",
            model: payload.model || "",
            workflow: "live_pcm_stream"
        });
        setVoiceExperienceState("listening");
        setVoiceStatus(translations[currentLanguage].voiceRecording);
        return;
    }
    if (payload.type === "partial") {
        const preview = String(payload.transcript || payload.delta || "").trim();
        if (preview) setVoiceStatus(preview.slice(-160));
        return;
    }
    if (payload.type === "final") {
        void acceptLiveTranscript(payload).catch(() => failLiveVoice());
        return;
    }
    if (payload.type === "error") failLiveVoice(payload.detail);
}

function failLiveVoice() {
    if (liveFinalReceived) return;
    markVoiceTiming("voice_failed", { stage: "transcription" });
    cleanupLiveSocket(false);
    voiceState = "idle";
    setVoiceComposerLocked(false);
    setVoiceStatus(translations[currentLanguage].voiceError);
    updateVoiceButton();
    hideVoiceExperience();
}

async function beginPcmCapture() {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) throw new Error("audio_context_unavailable");
    liveCaptureContext = new AudioContextClass({ latencyHint: "interactive" });
    await liveCaptureContext.resume();
    liveCaptureSource = liveCaptureContext.createMediaStreamSource(voiceStream);
    liveCaptureProcessor = liveCaptureContext.createScriptProcessor(2048, 1, 1);
    liveSilentGain = liveCaptureContext.createGain();
    liveSilentGain.gain.value = 0;
    liveCaptureProcessor.onaudioprocess = (audioEvent) => {
        if (liveVoiceSocket?.readyState !== WebSocket.OPEN || voiceState !== "recording") return;
        const channel = audioEvent.inputBuffer.getChannelData(0);
        liveVoiceSocket.send(pcm16At24k(channel, liveCaptureContext.sampleRate));
    };
    liveCaptureSource.connect(liveCaptureProcessor);
    liveCaptureProcessor.connect(liveSilentGain);
    liveSilentGain.connect(liveCaptureContext.destination);
}

async function startVoiceRecording() {
    if (chatbotConfig.voiceTransport === "openai_webrtc") {
        return window.JorMallWebRTC.start();
    }
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || isLeadGateOpen || isWaitingForResponse) {
        setVoiceStatus(translations[currentLanguage].voiceError);
        return;
    }
    try {
        cancelPendingVoiceReply = false;
        liveFinalReceived = false;
        stopBrowserSpeech();
        primeVoicePlayback();
        voiceStream = await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
        });
        const endpoint = chatbotConfig.voiceLiveTranscribeEndpoint;
        if (!endpoint) throw new Error("live_transcription_endpoint_missing");
        liveVoiceSocket = new WebSocket(liveSocketUrl(endpoint));
        liveVoiceSocket.binaryType = "arraybuffer";
        liveVoiceSocket.addEventListener("message", handleLiveMessage);
        liveVoiceSocket.addEventListener("error", () => failLiveVoice());
        liveVoiceSocket.addEventListener("close", () => {
            if (!liveFinalReceived && voiceState !== "idle") failLiveVoice();
        });
        await new Promise((resolve, reject) => {
            const timer = window.setTimeout(() => reject(new Error("live_socket_timeout")), 8000);
            liveVoiceSocket.addEventListener("open", () => { window.clearTimeout(timer); resolve(); }, { once: true });
            liveVoiceSocket.addEventListener("error", reject, { once: true });
        });
        liveVoiceSocket.send(JSON.stringify({
            type: "start",
            language: currentLanguage,
            lead_session_id: String(leadSessionId || "")
        }));
        await beginPcmCapture();
        mediaRecorder = { state: "recording" };
        voiceState = "recording";
        voiceStopPending = false;
        voiceRecordingLanguage = currentLanguage;
        window.JorMallVoiceTimings?.start(voiceRecordingLanguage);
        markVoiceTiming("recording_started", { workflow: "live_pcm_stream", sampleRate: 24000 });
        setVoiceExperienceState("listening");
        setVoiceComposerLocked(true);
        setVoiceStatus(translations[currentLanguage].voiceRecording);
        updateVoiceButton();
        voiceStopTimer = window.setTimeout(stopVoiceRecording, Number(chatbotConfig.voiceMaxRecordingSeconds || 45) * 1000);
    } catch (error) {
        cleanupLiveSocket(true);
        voiceState = "idle";
        setVoiceComposerLocked(false);
        setVoiceStatus(error?.name === "NotAllowedError" ? translations[currentLanguage].voicePermission : translations[currentLanguage].voiceError);
        updateVoiceButton();
        hideVoiceExperience();
    }
}

function stopVoiceRecording() {
    if (chatbotConfig.voiceTransport === "openai_webrtc") {
        return window.JorMallWebRTC.stopRecording();
    }
    if (voiceState !== "recording" || voiceStopPending) return;
    voiceStopPending = true;
    markVoiceTiming("recording_stop_requested");
    clearTimeout(voiceStopTimer);
    voiceStopTimer = null;
    window.setTimeout(() => {
        if (cancelCurrentRecording) {
            cancelCurrentRecording = false;
            cleanupLiveSocket(true);
            voiceState = "idle";
            setVoiceComposerLocked(false);
            updateVoiceButton();
            hideVoiceExperience();
        } else if (liveVoiceSocket?.readyState === WebSocket.OPEN) {
            stopVoiceTracks();
            voiceState = "transcribing";
            markVoiceTiming("recording_completed", { workflow: "live_pcm_stream" });
            markVoiceTiming("transcription_started", { workflow: "live_pcm_stream" });
            liveVoiceSocket.send(JSON.stringify({ type: "stop" }));
            setVoiceExperienceState("thinking");
            updateVoiceButton();
        } else {
            failLiveVoice();
        }
        voiceStopPending = false;
    }, 300);
}
