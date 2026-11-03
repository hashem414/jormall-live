/* Removable fourth voice-matrix option: GPT-Live WebRTC + existing RAG backend. */
window.JorMallWebRTC = (() => {
    let peer = null;
    let events = null;
    let microphone = null;
    let outputAudio = null;
    let ready = false;
    let closing = false;
    let awaitingBackend = false;
    let inputTranscript = "";
    let outputTranscript = "";
    let preBackendOutputTranscript = "";
    let answerAwaitingAudio = false;
    let answerAudioStarted = false;
    let commentaryAcknowledged = false;
    const pendingCommentaryEventIds = new Set();
    let activeDelegationId = "";
    let lastSavedAnswer = null;
    let delegationTimer = null;
    let stopTimer = null;
    const diagnostics = [];

    function record(type, detail = {}) {
        diagnostics.push({
            type,
            at: Math.round(performance.now() * 10) / 10,
            ...detail
        });
        if (diagnostics.length > 200) diagnostics.shift();
        window.dispatchEvent(new CustomEvent("jormall:webrtc", {
            detail: diagnostics[diagnostics.length - 1]
        }));
    }

    function send(payload) {
        if (!events || events.readyState !== "open") {
            throw new Error("webrtc_event_channel_not_ready");
        }
        events.send(JSON.stringify(payload));
    }

    function commentaryChunks(text) {
        const clean = String(text || "").replace(/\s+/g, " ").trim();
        if (!clean) return [];
        const chunks = [];
        let remaining = clean;
        while (remaining.length > 900) {
            let split = Math.max(
                remaining.lastIndexOf(". ", 900),
                remaining.lastIndexOf("؟ ", 900),
                remaining.lastIndexOf("! ", 900),
                remaining.lastIndexOf("; ", 900),
                remaining.lastIndexOf("، ", 900)
            );
            if (split < 360) split = remaining.lastIndexOf(" ", 900);
            if (split < 1) split = 900;
            chunks.push(remaining.slice(0, split + 1).trim());
            remaining = remaining.slice(split + 1).trim();
        }
        if (remaining) chunks.push(remaining);
        return chunks;
    }

    function sendSavedCommentary(answer, messageId, delegationId, prefix) {
        const chunks = commentaryChunks(answer);
        const eventIds = [];
        chunks.forEach((content, index) => {
            const eventId = `${prefix}_${messageId}_${Date.now()}_${index}`;
            eventIds.push(eventId);
            pendingCommentaryEventIds.add(eventId);
            send({
                type: "session.commentary.append",
                event_id: eventId,
                delegation_id: delegationId,
                content
            });
        });
        return eventIds;
    }

    async function currentOutputEnergy() {
        if (!peer) return 0;
        const stats = await peer.getStats();
        let energy = 0;
        stats.forEach((report) => {
            if ((report.type === "inbound-rtp" || report.type === "media-playout") &&
                (report.kind === "audio" || report.mediaType === "audio" || report.type === "media-playout")) {
                energy += Number(report.totalAudioEnergy || 0);
            }
        });
        return energy;
    }

    async function watchForAnswerAudio() {
        const baseline = await currentOutputEnergy().catch(() => 0);
        const started = performance.now();
        const timer = window.setInterval(async () => {
            if (!answerAwaitingAudio || answerAudioStarted || !peer) {
                window.clearInterval(timer);
                return;
            }
            const energy = await currentOutputEnergy().catch(() => baseline);
            if (energy > baseline + 0.000001) {
                answerAudioStarted = true;
                answerAwaitingAudio = false;
                window.clearInterval(timer);
                markVoiceTiming("tts_first_audio_byte", { workflow: "webrtc", evidence: "rtp_audio_energy" });
                markVoiceTiming("playback_started", { workflow: "webrtc", evidence: "rtp_audio_energy" });
                setVoiceExperienceState("speaking");
                record("answer_audio_started", {
                    evidence: "rtp_audio_energy",
                    waitMs: Math.round((performance.now() - started) * 10) / 10
                });
            }
        }, 25);
        window.setTimeout(() => window.clearInterval(timer), 15_000);
    }

    function stopTracks() {
        microphone?.getTracks().forEach((track) => track.stop());
        microphone = null;
    }

    function cleanup({ closeSession = true } = {}) {
        window.clearTimeout(delegationTimer);
        window.clearTimeout(stopTimer);
        delegationTimer = null;
        stopTimer = null;
        if (closeSession && ready && events?.readyState === "open" && !closing) {
            closing = true;
            try { send({ type: "session.close" }); } catch {}
        }
        stopTracks();
        if (outputAudio) {
            outputAudio.pause();
            outputAudio.srcObject = null;
        }
        outputAudio = null;
        try { events?.close(); } catch {}
        try { peer?.close(); } catch {}
        events = null;
        peer = null;
        ready = false;
        closing = false;
        awaitingBackend = false;
        activeDelegationId = "";
        inputTranscript = "";
        answerAwaitingAudio = false;
        commentaryAcknowledged = false;
        pendingCommentaryEventIds.clear();
    }

    function fail(stage, error) {
        record("failure", { stage, error: String(error?.message || error || "unknown").slice(0, 240) });
        markVoiceTiming("voice_failed", { stage });
        cleanup();
        voiceState = "idle";
        setVoiceComposerLocked(false);
        setVoiceStatus(translations[currentLanguage].voiceError);
        updateVoiceButton();
        hideVoiceExperience();
    }

    function waitForIce(connection) {
        if (connection.iceGatheringState === "complete") return Promise.resolve();
        return new Promise((resolve, reject) => {
            const timer = window.setTimeout(() => {
                connection.removeEventListener("icegatheringstatechange", onState);
                reject(new Error("webrtc_ice_timeout"));
            }, 10_000);
            function onState() {
                if (connection.iceGatheringState !== "complete") return;
                window.clearTimeout(timer);
                connection.removeEventListener("icegatheringstatechange", onState);
                resolve();
            }
            connection.addEventListener("icegatheringstatechange", onState);
            onState();
        });
    }

    async function runDelegation(delegationId) {
        if (awaitingBackend || !delegationId) return;
        const transcript = inputTranscript.trim();
        inputTranscript = "";
        if (!transcript) {
            fail("webrtc_transcript", new Error("empty_live_transcript"));
            return;
        }
        activeDelegationId = delegationId;
        awaitingBackend = true;
        const language = detectTextLanguage(transcript, currentLanguage);
        markVoiceTiming("transcription_completed", {
            detectedLanguage: language,
            provider: "openai",
            model: chatbotConfig.voiceWebrtcModel,
            workflow: "webrtc"
        });
        setVoiceExperienceState("thinking");
        voiceState = "transcribing";
        updateVoiceButton();
        record("delegation", { delegationId, transcript });
        try {
            await sendMessage(transcript, {
                voiceReply: true,
                voiceLanguage: language,
                webRtcDelegationId: delegationId
            });
        } catch (error) {
            fail("chat", error);
        }
    }

    function handleEvent(raw) {
        let event;
        try { event = JSON.parse(raw); } catch { return; }
        record("server_event", { eventType: event.type || "unknown" });
        if (event.type === "session.started") {
            ready = true;
            voiceState = "recording";
            setVoiceExperienceState("listening");
            setVoiceStatus(translations[currentLanguage].voiceRecording);
            updateVoiceButton();
            markVoiceTiming("transcription_headers", {
                provider: "openai",
                model: chatbotConfig.voiceWebrtcModel,
                workflow: "webrtc"
            });
            return;
        }
        if (event.type === "session.input_transcript.delta") {
            inputTranscript += String(event.delta || "");
            const preview = inputTranscript.trim();
            if (preview) setVoiceStatus(preview.slice(-160));
            return;
        }
        if (event.type === "session.output_transcript.delta") {
            const delta = String(event.delta || "");
            if (awaitingBackend || !lastSavedAnswer || !commentaryAcknowledged) {
                preBackendOutputTranscript += delta;
                record("pre_backend_output", { delta: delta.slice(0, 160) });
            } else {
                outputTranscript += delta;
                record("answer_output_transcript", { delta: delta.slice(0, 160) });
                if (answerAwaitingAudio && !answerAudioStarted) {
                    // Transcript is a latency fallback if the browser omits audio-energy stats.
                    answerAudioStarted = true;
                    answerAwaitingAudio = false;
                    markVoiceTiming("tts_first_audio_byte", { workflow: "webrtc", evidence: "output_transcript_proxy" });
                    markVoiceTiming("playback_started", { workflow: "webrtc", evidence: "output_transcript_proxy" });
                    setVoiceExperienceState("speaking");
                    record("answer_audio_started", { evidence: "output_transcript_proxy" });
                }
            }
            return;
        }
        if (event.type === "session.delegation.created" && event.delegation?.target === "client") {
            const delegationId = String(event.delegation.id || "");
            window.clearTimeout(delegationTimer);
            // Transcript deltas and the delegation event are independent streams.
            delegationTimer = window.setTimeout(() => void runDelegation(delegationId), 180);
            return;
        }
        if (event.type === "session.commentary.appended") {
            const clientEventId = String(event.client_event_id || "");
            record("commentary_accepted", { clientEventId });
            if (pendingCommentaryEventIds.has(clientEventId)) {
                pendingCommentaryEventIds.delete(clientEventId);
                if (!commentaryAcknowledged) {
                    commentaryAcknowledged = true;
                    answerAwaitingAudio = true;
                    void watchForAnswerAudio();
                }
            }
            return;
        }
        if (event.type === "session.closed") {
            record("session_closed", { usage: event.usage || null });
            cleanup({ closeSession: false });
            return;
        }
        if (event.type === "error") {
            fail("webrtc_provider", new Error(event.error?.message || "OpenAI Live error"));
        }
    }

    async function start() {
        if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || isLeadGateOpen || isWaitingForResponse) {
            setVoiceStatus(translations[currentLanguage].voiceError);
            return;
        }
        try {
            cleanup({ closeSession: false });
            cancelPendingVoiceReply = false;
            inputTranscript = "";
            outputTranscript = "";
            preBackendOutputTranscript = "";
            answerAwaitingAudio = false;
            answerAudioStarted = false;
            commentaryAcknowledged = false;
            pendingCommentaryEventIds.clear();
            lastSavedAnswer = null;
            voiceState = "transcribing";
            setVoiceComposerLocked(true);
            setVoiceExperienceState("warming");
            setVoiceStatus(currentLanguage === "ar" ? "جارٍ الاتصال بالصوت المباشر..." : "Connecting live voice...");
            updateVoiceButton();
            window.JorMallVoiceTimings?.start(currentLanguage);
            markVoiceTiming("recording_started", { workflow: "webrtc" });
            peer = new RTCPeerConnection();
            outputAudio = new Audio();
            outputAudio.autoplay = true;
            outputAudio.playsInline = true;
            outputAudio.addEventListener("playing", () => {
                record("remote_track_playing");
            });
            peer.addEventListener("track", (event) => {
                outputAudio.srcObject = event.streams[0] || new MediaStream([event.track]);
                void outputAudio.play().catch((error) => record("autoplay_blocked", { error: String(error) }));
            });
            microphone = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
            });
            for (const track of microphone.getAudioTracks()) peer.addTrack(track, microphone);
            events = peer.createDataChannel("oai-events");
            events.addEventListener("message", ({ data }) => handleEvent(data));
            events.addEventListener("close", () => {
                if (!closing && ready) fail("webrtc_channel", new Error("event_channel_closed"));
            });
            const offer = await peer.createOffer();
            await peer.setLocalDescription(offer);
            await waitForIce(peer);
            const sdp = peer.localDescription?.sdp;
            if (!sdp) throw new Error("webrtc_sdp_missing");
            const response = await fetch(chatbotConfig.voiceWebrtcSessionEndpoint, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    sdp,
                    language: currentLanguage,
                    lead_session_id: String(leadSessionId || "")
                })
            });
            if (!response.ok) {
                let detail = "";
                try {
                    const payload = await response.json();
                    detail = String(payload?.detail || "").slice(0, 320);
                } catch {}
                throw new Error(`webrtc_session_${response.status}${detail ? `: ${detail}` : ""}`);
            }
            const result = await response.json();
            if (!result?.transport?.sdp || !result?.session?.id) throw new Error("webrtc_answer_invalid");
            await peer.setRemoteDescription({ type: "answer", sdp: result.transport.sdp });
            record("session_created", { sessionId: result.session.id, model: chatbotConfig.voiceWebrtcModel });
            stopTimer = window.setTimeout(stopRecording, Number(chatbotConfig.voiceMaxRecordingSeconds || 45) * 1000);
        } catch (error) {
            fail("webrtc_connect", error);
        }
    }

    function stopRecording() {
        if (!ready || voiceState !== "recording") return;
        window.clearTimeout(stopTimer);
        stopTimer = null;
        microphone?.getAudioTracks().forEach((track) => { track.enabled = false; });
        voiceState = "transcribing";
        markVoiceTiming("recording_stop_requested", { workflow: "webrtc" });
        markVoiceTiming("recording_completed", { workflow: "webrtc" });
        markVoiceTiming("transcription_started", { workflow: "webrtc" });
        setVoiceExperienceState("thinking");
        setVoiceStatus(currentLanguage === "ar" ? "جارٍ فهم سؤالك..." : "Understanding your question...");
        updateVoiceButton();
    }

    async function deliverSavedAnswer({ answer, messageId, savedSessionId, delegationId }) {
        if (!answer || !messageId || !delegationId || delegationId !== activeDelegationId) {
            fail("saved_answer_contract", new Error("saved_message_or_delegation_missing"));
            return;
        }
        lastSavedAnswer = { answer, messageId, savedSessionId, delegationId };
        awaitingBackend = false;
        markVoiceTiming("tts_requested", {
            provider: "openai",
            model: chatbotConfig.voiceWebrtcModel,
            voice: chatbotConfig.voiceWebrtcVoice,
            messageId,
            savedSessionId,
            contract: "authorized_saved_message_delegation"
        });
        setVoiceExperienceState("preparing");
        outputTranscript = "";
        answerAwaitingAudio = false;
        answerAudioStarted = false;
        commentaryAcknowledged = false;
        pendingCommentaryEventIds.clear();
        const eventIds = sendSavedCommentary(answer, messageId, delegationId, "saved");
        record("saved_answer_sent", { messageId, savedSessionId, delegationId, characters: answer.length, chunks: eventIds.length });
        voiceState = "idle";
        setVoiceComposerLocked(false);
        updateVoiceButton();
    }

    async function replaySavedAnswer(answer, messageId, savedSessionId) {
        if (!ready || !lastSavedAnswer || lastSavedAnswer.messageId !== messageId) {
            setVoiceStatus(currentLanguage === "ar" ? "ابدأ محادثة صوتية جديدة لإعادة التشغيل." : "Start a new live voice turn to replay this answer.");
            return;
        }
        outputAudio?.play().catch(() => {});
        markVoiceTiming("tts_requested", { replay: true, provider: "openai", model: chatbotConfig.voiceWebrtcModel });
        commentaryAcknowledged = false;
        answerAwaitingAudio = false;
        answerAudioStarted = false;
        pendingCommentaryEventIds.clear();
        sendSavedCommentary(
            String(answer || lastSavedAnswer.answer),
            messageId,
            lastSavedAnswer.delegationId,
            "replay"
        );
        record("replay_requested", { messageId, savedSessionId });
    }

    function interruptPlayback() {
        if (awaitingBackend) return;
        if (outputAudio && !outputAudio.paused) {
            outputAudio.pause();
            record("playback_stopped");
        }
    }

    function snapshot() {
        return JSON.parse(JSON.stringify({
            ready,
            awaitingBackend,
            activeDelegationId,
            inputTranscript,
            outputTranscript,
            preBackendOutputTranscript,
            answerAudioStarted,
            commentaryAcknowledged,
            lastSavedAnswer,
            diagnostics
        }));
    }

    return { start, stopRecording, deliverSavedAnswer, replaySavedAnswer, interruptPlayback, snapshot, cleanup };
})();
