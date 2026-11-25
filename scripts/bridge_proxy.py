#!/usr/bin/env python3
"""Gemini bridge for the hosted Read-It-For-Me demo.

Why this exists: the hosting platform (Vercel) cannot hold the real
Gemini API key when the key is managed by Muse's secure vault — the
vault only releases a surrogate to registered hosts from this machine.
So the deployed FastAPI app calls this tiny bridge instead:

    POST /analyze  {"imageDataUrl": "data:image/jpeg;base64,...",
                    "prompt": "<full system+user prompt>"}
    -> {"text": "<model's raw reply>"}   (the app validates it as usual)

The bridge is deliberately dumb: all prompting, JSON validation and
safety rules live in the app. Run it on a machine that holds the key:

    GEMINI_API_KEY=...  python scripts/bridge_proxy.py          # direct key
    # or, under Muse, with the vault connector (no key in env):
    BRIDGE_CONNECTOR=custom.gemini-app python scripts/bridge_proxy.py

Env: BRIDGE_TOKEN (shared secret, checked via x-bridge-token header),
BRIDGE_PORT (default 5682), GEMINI_MODEL (default gemini-3.5-flash).
Expose it to the internet through a tunnel + webhook forwarder (the
reference deployment uses the existing ngrok domain + an n8n webhook
workflow named "ReadIt Bridge", path /webhook/readit-analyze).
"""

from __future__ import annotations

import base64  # noqa: F401  (kept for parity with the reference bridge)
import json
import os
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = os.environ.get("BRIDGE_TOKEN", "")
PORT = int(os.environ.get("BRIDGE_PORT", "5682"))
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
CONNECTOR = os.environ.get("BRIDGE_CONNECTOR", "")


def _apply_auth(req: urllib.request.Request) -> None:
    """Attach Gemini credentials: direct key, or vault surrogate."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        req.add_header("x-goog-api-key", key)
        return
    if CONNECTOR:
        import sys

        sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
        from dynamic_credentials import add_surrogate_to_request

        add_surrogate_to_request(
            req, CONNECTOR, allowed_hosts=["generativelanguage.googleapis.com"]
        )
        return
    raise RuntimeError("Neither GEMINI_API_KEY nor BRIDGE_CONNECTOR is set")


def _read_body(resp) -> bytes:
    if CONNECTOR and not os.environ.get("GEMINI_API_KEY"):
        from dynamic_credentials import read_response_body

        return read_response_body(resp)
    return resp.read()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # privacy: no request logging
        pass

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._json(200, {"ok": True, "service": "readit-bridge", "model": MODEL})

    def do_POST(self):
        if self.path.rstrip("/") != "/analyze":
            return self._json(404, {"error": "not found"})
        if TOKEN and self.headers.get("x-bridge-token") != TOKEN:
            return self._json(401, {"error": "unauthorised"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json(400, {"error": "invalid JSON body"})
        data_url = body.get("imageDataUrl", "")
        prompt = body.get("prompt", "")
        match = re.match(r"^data:(image/[a-zA-Z0-9+.-]+);base64,(.+)$", data_url, re.S)
        if not match or not prompt:
            return self._json(400, {"error": "imageDataUrl and prompt are required"})
        payload = {
            "contents": [{"parts": [
                {"inline_data": {"mime_type": match.group(1), "data": match.group(2)}},
                {"text": prompt},
            ]}],
            "generationConfig": {"temperature": 0.1},
        }
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            _apply_auth(req)
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(_read_body(resp).decode())
        except urllib.error.HTTPError as exc:
            return self._json(502, {"error": f"Gemini API failed with status {exc.code}"})
        except Exception as exc:
            return self._json(502, {"error": f"bridge upstream error: {type(exc).__name__}"})
        text = (
            (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}])[0]
            .get("text", "")
        )
        if not text:
            return self._json(502, {"error": "model returned no text"})
        self._json(200, {"text": text})


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
