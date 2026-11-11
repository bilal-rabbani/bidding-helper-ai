"""Daily limits are per model: skip only that model, then switch models. No real keys needed."""
import pytest

from core.llm_router import AllKeysFailed, LLMRouter
from tests.test_llm_router import Clock, Resp, gemini_ok

DAILY = Resp(429, text='{"error": {"message": "You exceeded your current quota", "details": '
                       '[{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}')
NOT_FOUND = Resp(404, text='{"error": {"message": "This model is no longer available to new users."}}')
M38, M37 = "gemini-3.8-flash", "gemini-3.7-flash"


class ModelHTTP:
    """script maps (key, model) to a list of answers; the last one repeats."""

    def __init__(self, models, script):
        self.models, self.script, self.calls = models, script, []

    def __call__(self, method, url, headers=None, json=None, timeout=None):
        headers = headers or {}
        key = headers.get("x-goog-api-key", "")
        if method == "GET":
            return Resp(200, {"models": [{"name": f"models/{m}", "supportedGenerationMethods": ["generateContent"]}
                                         for m in self.models]})
        model = url.rsplit("/models/", 1)[1].split(":")[0]
        self.calls.append((key, model))
        queue = self.script[(key, model)]
        return queue.pop(0) if len(queue) > 1 else queue[0]


def router(keys, models, script):
    clock = Clock()
    http = ModelHTTP(models, script)
    return LLMRouter({"gemini": keys}, http=http, clock=clock, sleep=clock.sleep), http


def test_daily_limit_skips_only_that_key_and_model():
    r, http = router(["g1", "g2"], [M38, M37], {
        ("g1", M38): [DAILY], ("g2", M38): [gemini_ok("from g2")]})
    res = r.complete("hi")
    assert res.text == "from g2" and res.model == M38
    assert any("daily limit" in n for n in res.notes)
    http.calls.clear()
    assert r.complete("again").text == "from g2"
    assert http.calls == [("g2", M38)]            # g1 is not asked again for this model


def test_switches_to_the_next_model_when_all_keys_used_the_daily_limit():
    r, _ = router(["g1", "g2"], [M38, M37], {
        ("g1", M38): [DAILY], ("g2", M38): [DAILY],
        ("g1", M37): [gemini_ok("from 3.7")], ("g2", M37): [gemini_ok("from 3.7")]})
    res = r.complete("hi")
    assert res.text == "from 3.7" and res.model == M37
    assert r.models["gemini"] == M37
    assert any("Switching" in n for n in res.notes)


def test_retired_model_moves_to_the_next_model():
    r, _ = router(["g1"], [M38, M37], {("g1", M38): [NOT_FOUND], ("g1", M37): [gemini_ok("ok")]})
    res = r.complete("hi")
    assert res.model == M37 and any("was not found" in n for n in res.notes)


def test_a_retired_model_is_not_asked_again_after_it_is_picked_by_hand():
    r, http = router(["g1"], [M38, M37], {("g1", M38): [NOT_FOUND], ("g1", M37): [gemini_ok("ok")]})
    r.complete("hi")
    r.set_model("gemini", M38)                      # the sidebar puts the old choice back
    http.calls.clear()
    assert r.complete("again").model == M37
    assert (("g1", M38)) not in http.calls


def test_everything_used_up_gives_a_clear_error():
    r, _ = router(["g1"], [M38], {("g1", M38): [DAILY]})
    with pytest.raises(AllKeysFailed) as e:
        r.complete("hi")
    assert "daily limit" in str(e.value)
