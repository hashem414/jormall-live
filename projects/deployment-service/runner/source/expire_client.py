#!/usr/bin/env python3
import json
import socket

request = json.dumps(
    {"operation": "expire", "actor": "preview-expiry-timer", "payload": {}},
    separators=(",", ":"),
).encode() + b"\n"

with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.settimeout(120)
    client.connect("/run/jormall-deployer/runner.sock")
    client.sendall(request)
    data = b""
    while b"\n" not in data:
        chunk = client.recv(65536)
        if not chunk:
            break
        data += chunk

response = json.loads(data)
if not response.get("ok"):
    raise SystemExit("preview expiry runner request failed")
