from core.llm_router import AllKeysFailed, LLMRouter, pick_default_model
from tests.test_llm_router import Clock, FakeHTTP, Resp, gemini_list, groq_list, groq_ok

NOT_FOUND = Resp(404, text='{"error": {"message": "models/x is not found"}}')


def test_groq_avoids_the_arabic_model_and_prefers_strong_ones():
    assert pick_default_model("groq", ["allam-2-7b", "llama-3.1-8b-instant", "gpt-oss-20b"]) == "gpt-oss-20b"
    assert pick_default_model("groq", ["allam-2-7b", "llama-3.3-70b-versatile", "openai/gpt-oss-120b"]) \
        == "llama-3.3-70b-versatile"
    assert pick_default_model("groq", ["allam-2-7b", "openai/gpt-oss-120b", "openai/gpt-oss-20b",
                                       "qwen/qwen3.8-27b"]) == "openai/gpt-oss-120b"
    assert pick_default_model("groq", ["allam-2-7b", "foo-70b", "bar-8b"]) == "foo-70b"
    assert pick_default_model("groq", ["allam-2-7b"]) == "allam-2-7b"


def router(keys, script):
    clock = Clock()
    return LLMRouter(keys, http=FakeHTTP(script), clock=clock, sleep=clock.sleep)


def test_missing_model_moves_on_to_the_other_provider():
    r = router({"gemini": ["g1"], "groq": ["q1"]}, {
        ("g1", "list"): [gemini_list()], ("g1", "generate"): [NOT_FOUND],
        ("q1", "list"): [groq_list()], ("q1", "generate"): [groq_ok("from groq")]})
    res = r.complete("hi")
    assert res.provider == "groq" and res.text == "from groq"
    assert any("was not found" in n for n in res.notes)


def test_missing_model_with_no_other_provider_gives_a_clear_error():
    r = router({"gemini": ["g1"]}, {("g1", "list"): [gemini_list()], ("g1", "generate"): [NOT_FOUND]})
    try:
        r.complete("hi")
    except AllKeysFailed as e:
        assert "was not found" in str(e)
    else:
        raise AssertionError("expected AllKeysFailed")
