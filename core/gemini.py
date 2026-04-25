"""
Gemini free-tier helper.
Uses stdlib urllib only â€” no extra SDK dependency.
Requires Pillow for clipboard image capture (pip install Pillow).
"""
from __future__ import annotations

import base64
import ctypes
import io
import json
import re
import urllib.error
import urllib.request

_BASE    = "https://generativelanguage.googleapis.com/v1beta"
_GEN_URL = _BASE + "/models/{model}:generateContent?key={key}"
_MODELS  = [
    "gemini-3.1-flash-live-preview",
    "gemini-3.1-flash-lite-preview",
]

DEFAULT_PROMPT = (
    "Give me the exact content of what I sent in a clean, formatted form. "
    "If it contains text or code, extract it exactly. "
    "If it is a table or structured data, preserve the layout. "
    "Output only the content â€” no explanations."
)


def call_gemini(api_key: str, prompt: str,
                image_bytes: bytes | None = None) -> str:
    """Send prompt (+ optional image) to Gemini; return response text."""
    parts: list = [{"text": prompt}]
    if image_bytes:
        parts.append({
            "inline_data": {
                "mime_type": "image/png",
                "data": base64.b64encode(image_bytes).decode("ascii"),
            }
        })
    body = json.dumps({"contents": [{"parts": parts}]}).encode("utf-8")

    last_err = ""
    for model in _MODELS:
        url = _GEN_URL.format(model=model, key=api_key)
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            last_err = _friendly_error(exc.code, raw)
            if exc.code == 404:
                continue
            raise RuntimeError(last_err) from exc

    raise RuntimeError(last_err or "No available Gemini model found.")


def _friendly_error(code: int, raw: str) -> str:
    try:
        msg   = json.loads(raw)["error"]["message"]
        short = msg.split("\n")[0].split("For more information")[0].strip().rstrip(".")
        retry = ""
        m = re.search(r'"retryDelay":\s*"(\d+)s"', raw)
        if m:
            retry = f" Retry in {m.group(1)}s."
        return f"HTTP {code}: {short}.{retry}"
    except Exception:
        return f"HTTP {code}: {raw[:200]}"


def clipboard_image() -> bytes | None:
    """Return clipboard image as PNG bytes, or None."""
    try:
        from PIL import Image, ImageGrab
        img = ImageGrab.grabclipboard()
        if isinstance(img, Image.Image):
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="PNG")
            return buf.getvalue()
    except Exception:
        pass
    return None


def clipboard_text() -> str:
    """Return clipboard text via Win32 API."""
    CF_UNICODETEXT = 13
    user32   = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.GlobalLock.restype = ctypes.c_void_p
    if not user32.OpenClipboard(None):
        return ""
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        p = kernel32.GlobalLock(h)
        if not p:
            return ""
        text = ctypes.wstring_at(p)
        kernel32.GlobalUnlock(h)
        return text
    except Exception:
        return ""
    finally:
        user32.CloseClipboard()
