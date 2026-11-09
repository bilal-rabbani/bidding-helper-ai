"""Phase 4a tests: key switching, invalid keys, waiting, model lists. No real keys or internet."""
import json as jsonlib

import pytest

from core.llm_router import (AllKeysFailed, KeyState, LLMRequestError, LLMRouter,
                             _is_chat_name, parse_keys, pick_default_model)


class Resp:
    def __init__(self, status=200, data=None, text=None, headers=None):
        self.status_code = status
        self._data = data or {}
        self.text = text if text is not None else jsonlib.dumps(self._data)
        self.headers = headers or {}

    def json(self):
        return self._data


def gemini_list():
    return Resp(200, {"models": [
        {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]}]})


def gemini_ok(text="hi"):
    return Resp(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})


def groq_list():
    return Resp(200, {"data": [{"id": "llama-3.3-70b-versatile"}, {"id": "whisper-large-v3"}]})


def groq_ok(text="hi"):
    return Resp(200, {"choices": [{"message": {"content": text}}]})


BAD_KEY = Resp(400, text='{"error": {"message": "API key not valid. Please pass a valid API key."}}')


class FakeHTTP:
    """script maps (key, 'list' or 'generate') to a list of answers; the last one repeats."""

    def __init__(self, script):
        self.script, self.calls = script, []

    def __call__(self, method, url, headers=None, json=None, timeout=None):
        headers = headers or {}
        key = headers.get("x-goog-api-key") or headers.get("Authorization", "").replace("Bearer ", "")
        kind = "list" if method == "GET" else "generate"
        self.calls.append((key, kind))
        queue = self.script[(key, kind)]
        return queue.pop(0) if len(queue) > 1 else queue[0]


class Clock:
    def __init__(self):
        self.now, self.slept = 1000.0, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def router(keys, script, **kw):
    clock = Clock()
    http = FakeHTTP(script)
    r = LLMRouter(keys, http=http, clock=clock, sleep=clock.sleep, **kw)
    return r, http, clock


def test_parse_keys():
    assert parse_keys('a1\nb2, "c3"  a1') == ["a1", "b2", "c3"]
    assert parse_keys("") == [] and parse_keys(None) == []
    assert parse_keys(["x", " y "]) == ["x", "y"]


def test_model_filter_and_defaults():
    assert not _is_chat_name("text-embedding-004") and not _is_chat_name("whisper-large-v3")
    assert _is_chat_name("gemini-2.5-flash")
    gem = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
    assert pick_default_model("gemini", gem) == "gemini-2.5-flash"
    assert pick_default_model("groq", ["gemma2-9b-it", "llama-3.3-70b-versatile"]) == "llama-3.3-70b-versatile"
    assert pick_default_model("groq", []) == ""


def test_first_key_works_and_model_is_picked_from_the_list():
    r, http, _ = router({"gemini": ["g1"]}, {("g1", "list"): [gemini_list()],
                                             ("g1", "generate"): [gemini_ok("hello")]})
    res = r.complete("hi")
    assert (res.text, res.provider, res.model) == ("hello", "gemini", "gemini-2.5-flash")
    assert res.notes == []


def test_switches_to_next_key_when_one_is_rate_limited():
    r, http, _ = router({"gemini": ["g1", "g2"]}, {
        ("g1", "list"): [gemini_list()], ("g2", "list"): [gemini_list()],
        ("g1", "generate"): [Resp(429, text="quota")], ("g2", "generate"): [gemini_ok("from g2")]})
    res = r.complete("hi")
    assert res.text == "from g2" and "hit its limit" in " ".join(res.notes)
    http.calls.clear()
    assert r.complete("again").text == "from g2"
    assert http.calls == [("g2", "generate")]          # g1 is resting, so it is skipped


def test_falls_back_to_the_other_provider():
    r, _, _ = router({"gemini": ["g1"], "groq": ["q1"]}, {
        ("g1", "list"): [gemini_list()], ("g1", "generate"): [Resp(429, text="quota")],
        ("q1", "list"): [groq_list()], ("q1", "generate"): [groq_ok("from groq")]})
    res = r.complete("hi")
    assert res.provider == "groq" and res.text == "from groq" and res.model == "llama-3.3-70b-versatile"


def test_primary_provider_goes_first():
    r, _, _ = router({"gemini": ["g1"], "groq": ["q1"]}, {
        ("g1", "list"): [gemini_list()], ("g1", "generate"): [gemini_ok()],
        ("q1", "list"): [groq_list()], ("q1", "generate"): [groq_ok("groq first")]}, primary="groq")
    assert r.complete("hi").provider == "groq"


def test_invalid_key_is_marked_and_skipped():
    r, http, _ = router({"gemini": ["g1", "g2"]}, {
        ("g1", "list"): [gemini_list()], ("g2", "list"): [gemini_list()],
        ("g1", "generate"): [BAD_KEY], ("g2", "generate"): [gemini_ok("ok")]})
    assert r.complete("hi").text == "ok"
    assert [s["status"] for s in r.status()] == ["invalid", "ok"]
    http.calls.clear()
    r.complete("again")
    assert ("g1", "generate") not in http.calls


def test_waits_briefly_then_retries():
    r, _, clock = router({"gemini": ["g1"]}, {
        ("g1", "list"): [gemini_list()],
        ("g1", "generate"): [Resp(429, headers={"Retry-After": "2"}), gemini_ok("later")]})
    res = r.complete("hi")
    assert res.text == "later" and len(clock.slept) == 1 and 2 <= clock.slept[0] <= 3


def test_long_limit_is_reported_without_waiting():
    r, _, clock = router({"gemini": ["g1", "g2"]}, {
        ("g1", "list"): [gemini_list()], ("g2", "list"): [gemini_list()],
        ("g1", "generate"): [Resp(429, headers={"Retry-After": "3600"})],
        ("g2", "generate"): [Resp(429, headers={"Retry-After": "3600"})]})
    with pytest.raises(AllKeysFailed) as e:
        r.complete("hi")
    assert "rate limited" in str(e.value) and clock.slept == []


def test_bad_request_is_not_blamed_on_the_key():
    r, _, _ = router({"gemini": ["g1"]}, {
        ("g1", "list"): [gemini_list()],
        ("g1", "generate"): [Resp(400, text='{"error": {"message": "Request too large"}}')]})
    with pytest.raises(LLMRequestError):
        r.complete("hi")
    assert r.status()[0]["status"] == "ok"


def test_keys_never_appear_in_messages():
    key = "AI" + "za" + "B" * 35                      # a fake key, built here so the scanner stays quiet
    r, _, _ = router({"gemini": [key]}, {
        (key, "list"): [gemini_list()], (key, "generate"): [Resp(500, text=f"boom {key}")]})
    with pytest.raises(AllKeysFailed) as e:
        r.complete("hi")
    assert key not in str(e.value) and all(key not in n for n in e.value.notes)
    assert key not in repr(KeyState("gemini", key, "label"))
    assert key not in repr(r.status())


def test_test_keys_report():
    r, _, _ = router({"gemini": ["g1", "g2", "g3"]}, {
        ("g1", "list"): [gemini_list()], ("g2", "list"): [BAD_KEY],
        ("g3", "list"): [Resp(429, text="quota")]})
    report = r.test_keys()
    assert [x["status"] for x in report] == ["ok", "invalid", "ok"]
    assert "limit" in report[2]["message"]


def test_no_keys_is_refused():
    with pytest.raises(Exception):
        LLMRouter({"gemini": ""}).complete("hi")
