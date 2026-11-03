"""Versioned framing around PCM s16le, mono, 24 kHz. Zero means complete."""
import json
import struct

MEDIA_TYPE = 'application/x-jormall-pcm'
FORMAT = 'pcm-s16le-24000-mono-framed-v1'
MAX_FRAME = 1024 * 1024
ERROR = 0xFFFFFFFF


def pcm_frame(data):
    if not data or len(data) % 2 or len(data) > MAX_FRAME:
        raise ValueError('Invalid PCM frame')
    return struct.pack('<I', len(data)) + data


def completion_frame():
    return struct.pack('<I', 0)


def error_frame(code='voice_generation_failed'):
    payload = json.dumps({'error': code}).encode()
    return struct.pack('<II', ERROR, len(payload)) + payload


def read_frames(stream):
    def exact(size):
        data = bytearray()
        while len(data) < size:
            chunk = stream.read(size-len(data))
            if not chunk:
                raise ValueError('Voice stream ended before completion')
            data.extend(chunk)
        return bytes(data)
    while True:
        size = struct.unpack('<I', exact(4))[0]
        if size == 0:
            if stream.read(1):
                raise ValueError('Unexpected bytes after completion')
            return
        if size == ERROR:
            count = struct.unpack('<I', exact(4))[0]
            if count > 4096: raise ValueError('Invalid voice error frame')
            raise ValueError(json.loads(exact(count)).get('error', 'voice_generation_failed'))
        if size > MAX_FRAME or size % 2:
            raise ValueError('Invalid voice frame')
        yield exact(size)
