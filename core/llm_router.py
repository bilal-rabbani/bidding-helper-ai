"""Talks to Gemini and Groq with several free API keys and switches keys when one runs out.

Plain HTTPS calls, no LLM library. Keys are never printed or saved: they live
only inside the router object, and error texts have them blanked out.
"""
import re
import time
from dataclasses import dataclass, field

import requests

TIMEOUT = 60
DEFAULT_COOLDOWN = 60        # seconds a rate-limited key rests when the provider gives no hint
TEMP_COOLDOWN = 20           # seconds after a temporary server problem
PER_DAY_COOLDOWN = 3600      # when the limit looks like a daily one
USER_AGENT = "bidding-helper-ai/0.1"


class LLMError(Exception):
    pass


class LLMRequestError(LLMError):
    """The request itself is wrong (bad model name, too long, blocked). Another key will not help."""


class AllKeysFailed(LLMError):
    def __init__(self, message, notes=None):
        super().__init__(message)
        self.notes = notes or []


# ------------------------------------------------------------------ providers
_NOT_CHAT = ("embed", "whisper", "tts", "guard", "orpheus", "imagen", "image", "aqa",
             "live", "audio", "robotics", "computer-use", "veo", "transcribe")


def _is_chat_name(name: str) -> bool:
    n = name.lower()
    return not any(x in n for x in _NOT_CHAT)


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GROQ_BASE = "https://api.groq.com/openai/v1"


def _gemini_list(key):
    return ("GET", f"{GEMINI_BASE}/models?pageSize=200", {"x-goog-api-key": key}, None)


def _gemini_models(data):
    out = []
    for m in data.get("models", []):
        name = (m.get("name") or "").replace("models/", "")
        if "generateContent" in m.get("supportedGenerationMethods", []) and name and _is_chat_name(name):
            out.append(name)
    return sorted(out)


def _gemini_generate(key, model, system, prompt, temperature, max_tokens):
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    return ("POST", f"{GEMINI_BASE}/models/{model}:generateContent",
            {"x-goog-api-key": key, "Content-Type": "application/json"}, body)


def _gemini_text(data):
    cands = data.get("candidates") or []
    if not cands:
        return ""
    parts = (cands[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts)


def _groq_list(key):
    return ("GET", f"{GROQ_BASE}/models", {"Authorization": f"Bearer {key}"}, None)


def _groq_models(data):
    return sorted(m["id"] for m in data.get("data", []) if m.get("id") and _is_chat_name(m["id"]))


def _groq_generate(key, model, system, prompt, temperature, max_tokens):
    messages = ([{"role": "system", "content": system}] if system else [])
    messages.append({"role": "user", "content": prompt})
    body = {"model": model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens}
    return ("POST", f"{GROQ_BASE}/chat/completions",
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, body)


def _groq_text(data):
    choices = data.get("choices") or []
    return ((choices[0].get("message") or {}).get("content") or "") if choices else ""


PROVIDERS = {
    "gemini": {"label": "Gemini", "list": _gemini_list, "models": _gemini_models,
               "generate": _gemini_generate, "text": _gemini_text},
    "groq": {"label": "Groq", "list": _groq_list, "models": _groq_models,
             "generate": _groq_generate, "text": _groq_text},
}


GROQ_PREFERRED = ("llama-3.3-70b", "gpt-oss-120b", "llama-3.1-70b", "qwen3-32b",
                  "llama-4-maverick", "llama-4-scout", "gpt-oss-20b", "llama-3.1-8b")
GROQ_AVOID = ("allam", "compound", "saba")      # not suited to short instruction tasks


def pick_default_model(provider: str, models: list) -> str:
    """A sensible starting model from the list the provider returned."""
    if not models:
        return ""
    if provider == "groq":
        for pattern in GROQ_PREFERRED:
            for m in models:
                if pattern in m:
                    return m
        usable = [m for m in models if not any(x in m for x in GROQ_AVOID)] or models

        def size(m):
            found = re.findall(r"(\d+(?:\.\d+)?)b", m)
            return float(found[0]) if found else 0.0

        return max(usable, key=size)

    def version(m):
        found = re.search(r"gemini-(\d+(?:\.\d+)?)", m)
        return float(found.group(1)) if found else 0.0

    skip = ("lite", "preview", "exp", "thinking", "8b", "image")
    flash = [m for m in models if "flash" in m and not any(x in m for x in skip)]
    pool = flash or [m for m in models if "flash" in m] or models
    return max(pool, key=version)


# ------------------------------------------------------------------ helpers
def parse_keys(text) -> list:
    """Split pasted keys (one per line, or separated by commas/spaces). Removes repeats."""
    if text is None:
        return []
    items = text if isinstance(text, (list, tuple)) else re.split(r"[\s,;]+", str(text))
    keys = []
    for item in items:
        k = str(item).strip().strip("\"'")
        if k and k not in keys:
            keys.append(k)
    return keys


def _scrub(text, key=None) -> str:
    text = str(text or "")
    if key:
        text = text.replace(key, "***")
    text = re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "***", text)
    return re.sub(r"gsk_[0-9A-Za-z]{16,}", "***", text)


def _json(resp) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _retry_after(headers, text):
    for k, v in (headers or {}).items():
        if str(k).lower() == "retry-after":
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    m = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', text or "")
    if m:
        return float(m.group(1))
    m = re.search(r"try again in (?:(\d+)m)?(\d+(?:\.\d+)?)s", text or "")
    if m:
        return int(m.group(1) or 0) * 60 + float(m.group(2))
    return None


def _classify(status, text, headers):
    """Returns (kind, cooldown seconds). kind: rate_limit | temporary | bad_key | bad_model | bad_request."""
    low = (text or "").lower()
    retry = _retry_after(headers, text)
    if status == 429 or (status == 403 and "quota" in low):
        if retry is None:
            retry = PER_DAY_COOLDOWN if ("perday" in low or "per day" in low) else DEFAULT_COOLDOWN
        return "rate_limit", retry
    if status in (500, 502, 503, 504):
        return "temporary", retry or TEMP_COOLDOWN
    if status in (401, 403) or (status == 400 and ("api key not valid" in low or "api_key_invalid" in low)):
        return "bad_key", 0
    if status == 404:
        return "bad_model", 0
    return "bad_request", 0


def _error_message(resp, key) -> str:
    err = _json(resp).get("error")
    msg = err.get("message") if isinstance(err, dict) else None
    return _scrub(msg or getattr(resp, "text", "") or f"HTTP {resp.status_code}", key)[:200]


def _default_http(method, url, headers=None, json=None, timeout=TIMEOUT):
    merged = {"User-Agent": USER_AGENT}
    merged.update(headers or {})
    return requests.request(method, url, headers=merged, json=json, timeout=timeout)


# ------------------------------------------------------------------ the router
@dataclass
class KeyState:
    provider: str
    key: str = field(repr=False)          # never shown when printed
    label: str = ""
    status: str = "untested"              # untested | ok | invalid
    cooldown_until: float = 0.0


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    key_label: str
    notes: list = field(default_factory=list)   # e.g. "Gemini key 1 hit its limit"


class LLMRouter:
    def __init__(self, keys: dict, models: dict = None, primary: str = None,
                 http=None, clock=time.monotonic, sleep=time.sleep, max_wait: float = 15):
        self.http = http or _default_http
        self.clock, self.sleep, self.max_wait = clock, sleep, max_wait
        self.keys = {}
        for provider, value in keys.items():
            if provider not in PROVIDERS:
                continue
            ks = parse_keys(value)
            if ks:
                name = PROVIDERS[provider]["label"]
                self.keys[provider] = [
                    KeyState(provider, k, f"{name} key {i + 1} (...{k[-4:]})")
                    for i, k in enumerate(ks)]
        self.models = dict(models or {})
        self.primary = primary
        self._cursor = {p: 0 for p in self.keys}
        self._model_cache = {}

    # ---- information for the screen
    def providers(self) -> list:
        order = list(self.keys)
        if self.primary in order:
            order.remove(self.primary)
            order.insert(0, self.primary)
        return order

    def status(self) -> list:
        return [{"label": s.label, "provider": s.provider, "status": s.status,
                 "cooling_seconds": max(0, round(s.cooldown_until - self.clock()))}
                for states in self.keys.values() for s in states]

    def set_model(self, provider, model):
        self.models[provider] = model

    def _cooling(self, st) -> float:
        return st.cooldown_until - self.clock()

    # ---- sending one request with one key
    def _send(self, st, request):
        method, url, headers, body = request
        try:
            resp = self.http(method, url, headers=headers, json=body, timeout=TIMEOUT)
        except requests.RequestException as e:
            return "temporary", None, f"network problem ({type(e).__name__})", TEMP_COOLDOWN
        if resp.status_code == 200:
            return "ok", resp, "", 0
        kind, cooldown = _classify(resp.status_code, getattr(resp, "text", ""),
                                   getattr(resp, "headers", {}))
        return kind, resp, _error_message(resp, st.key), cooldown

    def _apply_failure(self, st, kind, msg, cooldown) -> str:
        if kind in ("rate_limit", "temporary"):
            st.cooldown_until = self.clock() + cooldown
            if kind == "rate_limit":
                return f"{st.label} hit its limit (resting about {int(cooldown)}s)"
            return f"{st.label} had a temporary problem: {msg}"
        if kind == "bad_key":
            st.status = "invalid"
            return f"{st.label} was rejected: {msg}"
        return f"{st.label}: {msg}"

    # ---- models
    def list_models(self, provider, refresh=False) -> list:
        if provider not in self.keys:
            raise LLMError(f"No {provider} keys were given.")
        if not refresh and provider in self._model_cache:
            return self._model_cache[provider]
        spec, notes = PROVIDERS[provider], []
        for st in self.keys[provider]:
            if st.status == "invalid" or self._cooling(st) > 0:
                continue
            kind, resp, msg, cooldown = self._send(st, spec["list"](st.key))
            if kind == "ok":
                st.status = "ok"
                self._model_cache[provider] = spec["models"](_json(resp))
                return self._model_cache[provider]
            notes.append(self._apply_failure(st, kind, msg, cooldown))
        raise AllKeysFailed("Could not get the model list. " + "; ".join(notes), notes)

    def model_for(self, provider) -> str:
        if not self.models.get(provider):
            self.models[provider] = pick_default_model(provider, self.list_models(provider))
        return self.models[provider]

    # ---- check every key
    def test_keys(self) -> list:
        report = []
        for states in self.keys.values():
            for st in states:
                kind, _, msg, cooldown = self._send(st, PROVIDERS[st.provider]["list"](st.key))
                if kind == "ok":
                    st.status, text = "ok", "works"
                elif kind == "rate_limit":
                    st.status = "ok"
                    st.cooldown_until = self.clock() + cooldown
                    text = "key is valid but is at its limit right now"
                else:
                    text = self._apply_failure(st, kind, msg, cooldown)
                report.append({"label": st.label, "provider": st.provider,
                               "status": st.status, "message": text})
        return report

    # ---- ask a question
    def _soonest(self, order):
        waits = [self._cooling(s) for p in order for s in self.keys.get(p, [])
                 if s.status != "invalid" and self._cooling(s) > 0]
        return min(waits) if waits else None

    def complete(self, prompt, system="", providers=None, temperature=0.2, max_tokens=4096) -> LLMResult:
        order = [p for p in (providers or self.providers()) if p in self.keys]
        if not order:
            raise LLMError("No API keys were given.")
        notes = []
        for attempt in range(2):
            for provider in order:
                states = self.keys[provider]
                try:
                    model = self.model_for(provider)
                except AllKeysFailed as e:
                    notes.extend(e.notes)
                    continue
                n = len(states)
                for offset in range(n):
                    idx = (self._cursor[provider] + offset) % n
                    st = states[idx]
                    if st.status == "invalid" or self._cooling(st) > 0:
                        continue
                    request = PROVIDERS[provider]["generate"](
                        st.key, model, system, prompt, temperature, max_tokens)
                    kind, resp, msg, cooldown = self._send(st, request)
                    if kind == "ok":
                        text = PROVIDERS[provider]["text"](_json(resp))
                        if not text.strip():
                            raise LLMRequestError(
                                "The model returned an empty answer (it may have been blocked).")
                        st.status = "ok"
                        self._cursor[provider] = (idx + 1) % n
                        if notes:
                            notes.append(f"Answered by {st.label} using {model}.")
                        return LLMResult(text, provider, model, st.label, notes)
                    if kind == "bad_model":
                        notes.append(f"The model '{model}' was not found for "
                                     f"{PROVIDERS[provider]['label']}; trying the next provider.")
                        break
                    if kind == "bad_request":
                        raise LLMRequestError(msg)
                    notes.append(self._apply_failure(st, kind, msg, cooldown))
            wait = self._soonest(order)
            if attempt == 0 and wait is not None and wait <= self.max_wait:
                self.sleep(wait + 0.5)
                notes.append(f"Waited {wait:.0f}s for a key to recover.")
                continue
            break
        wait = self._soonest(order)
        if wait is not None:
            raise AllKeysFailed(f"All keys are rate limited. Try again in about {int(wait)} seconds.", notes)
        raise AllKeysFailed("No key could answer. " + "; ".join(notes), notes)
