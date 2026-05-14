"""
Gemini free-tier helper.
Uses stdlib urllib only - no extra SDK dependency.
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

_BASE     = "https://generativelanguage.googleapis.com/v1beta"
_GEN_URL  = _BASE + "/models/{model}:generateContent?key={key}"
_LIST_URL = _BASE + "/models?key={key}"

# Last-resort fallback used only when the live ListModels call fails
# (no network, bad key, Google outage). Free-tier-only flash variants —
# names that Google currently advertises as the cheapest stable models.
_FALLBACK_MODELS = [
    "gemini-3.1-flash-lite",
]

# Filtered out: anything that historically requires billing. Catches all
# pro tiers regardless of version, plus the rare "ultra" lineage.
_PAID_TIER_MARKERS = ("pro", "ultra")

# Per-process cache so we only ListModels once per session per API key.
_MODELS_CACHE: dict[str, list[str]] = {}

# Name of the model that successfully answered the most recent call_gemini().
# Read via current_model() — callers display it in their status / result UI.
_LAST_USED_MODEL: str | None = None


def current_model() -> str | None:
    """Return the model that last successfully answered a `call_gemini` call,
    or None if no call has succeeded yet this session."""
    return _LAST_USED_MODEL

DEFAULT_PROMPT = (
    "Give me the exact content of what I sent in a clean, formatted form. "
    "If it contains text or code, extract it exactly. "
    "If it is a table or structured data, preserve the layout. "
    "Output only the content - no explanations."
)


def _rank_models(names: list[str]) -> list[str]:
    """Order models so the best free-tier candidate comes first.

    Priority (lower tuple value wins):
      1. stable over preview / experimental
      2. higher version number — newest generation first
      3. `lite` over non-lite within a tier (cheapest within free tier)
    `pro` / `ultra` are already excluded upstream so they never appear here.
    """
    def key(m: str):
        is_unstable = ("preview" in m) or ("exp" in m)
        match = re.search(r"(\d+)\.(\d+)", m)
        if match:
            major, minor = int(match.group(1)), int(match.group(2))
        else:
            major, minor = 0, 0
        is_not_lite = "lite" not in m
        return (is_unstable, -major, -minor, is_not_lite)
    return sorted(names, key=key)


def _discover_models(api_key: str) -> list[str]:
    """Ask Google which models this key can use, then keep only free-tier
    flash variants. Falls back to a hard-coded list on any failure so the
    caller always gets something to try."""
    try:
        url = _LIST_URL.format(key=api_key)
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception:
        return list(_FALLBACK_MODELS)

    candidates: list[str] = []
    for m in data.get("models", []):
        name = m.get("name", "")
        if not name.startswith("models/"):
            continue
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        bare = name[len("models/"):]
        lo = bare.lower()
        # Free-tier guard: skip every variant that historically costs money.
        if any(marker in lo for marker in _PAID_TIER_MARKERS):
            continue
        candidates.append(bare)

    return _rank_models(candidates) or list(_FALLBACK_MODELS)


def _get_models(api_key: str) -> list[str]:
    if api_key not in _MODELS_CACHE:
        _MODELS_CACHE[api_key] = _discover_models(api_key)
    return _MODELS_CACHE[api_key]


def call_gemini(api_key: str, prompt: str,
                image_bytes: bytes | None = None) -> str:
    """Send prompt (+ optional image) to Gemini; return response text.

    The model list is fetched once per session via Google's ListModels API
    (free-tier candidates only), then iterated in preference order with the
    same 404-fallthrough behaviour as before."""
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
    for model in _get_models(api_key):
        url = _GEN_URL.format(model=model, key=api_key)
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            global _LAST_USED_MODEL
            _LAST_USED_MODEL = model
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
    user32.GetClipboardData.restype  = ctypes.c_void_p
    kernel32.GlobalLock.restype      = ctypes.c_void_p
    kernel32.GlobalLock.argtypes     = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes   = [ctypes.c_void_p]
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
