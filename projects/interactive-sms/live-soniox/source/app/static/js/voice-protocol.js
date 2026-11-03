/* PCM transport v1. Completion and provider errors are explicit, independent of HTTP chunks. */
window.JorMallVoiceProtocol = (() => {
    async function* decodeReader(reader) {
        let pending = new Uint8Array(0), complete = false;
        async function exact(size) {
            while (pending.length < size) {
                const {value, done} = await reader.read();
                if (done) throw new Error("voice_stream_incomplete");
                const joined = new Uint8Array(pending.length + value.length);
                joined.set(pending); joined.set(value, pending.length); pending = joined;
            }
            const out = pending.slice(0, size); pending = pending.slice(size); return out;
        }
        async function count() { const bytes = await exact(4); return new DataView(bytes.buffer).getUint32(0, true); }
        try {
            while (true) {
                const size = await count();
                if (size === 0) {
                    if (pending.length || !(await reader.read()).done) throw new Error("voice_trailing_audio");
                    complete = true; return;
                }
                if (size === 0xFFFFFFFF) {
                    const length = await count();
                    if (length > 4096) throw new Error("voice_invalid_error");
                    const error = JSON.parse(new TextDecoder().decode(await exact(length)));
                    throw new Error(error.error || "voice_generation_failed");
                }
                if (size > 1048576 || size % 2) throw new Error("voice_invalid_frame");
                yield await exact(size);
            }
        } finally {
            if (!complete) await reader.cancel().catch(() => {});
            reader.releaseLock();
        }
    }
    function decode(response) { return decodeReader(response.body.getReader()); }
    function pcmResponse(response) {
        const reader = response.body.getReader();
        const frames = decodeReader(reader);
        return new Response(new ReadableStream({
            async pull(controller) {
                try { const {value, done} = await frames.next(); if (done) controller.close(); else controller.enqueue(value); }
                catch (error) { controller.error(error); }
            },
            async cancel() { await reader.cancel().catch(() => {}); await frames.return(); }
        }), {headers: {"Content-Type": "audio/L16;rate=24000;channels=1"}});
    }
    return {decode, pcmResponse};
})();
