import json

import httpx

from fakes import FakeLLM
from maestro.baseline import evaluate_baseline
from maestro.contract import Criterion, evaluate
from maestro.llm import LLMResponse, OllamaClient
from test_contract import ANSWERS, CHECKLIST, request


class OnePrompt:
    """Answers the one-prompt baseline with a fixed object and records what it was asked."""

    model = "fake-judge"

    def __init__(self, answers):
        self.answers = answers
        self.seen = []

    def complete(self, system, user, schema, think=None):
        self.seen.append((system, user, schema))
        return LLMResponse(content=json.dumps(self.answers, ensure_ascii=False), duration_ms=1,
                           prompt_tokens=100, completion_tokens=50)


def _criteria():
    return [Criterion(**c) for c in CHECKLIST]


def test_baseline_answers_every_criterion_in_one_call():
    criteria = _criteria()
    answers = {c.code: {"why": "x", "answer": "yes", "evidence": ["M3"]} for c in criteria}
    scale = next(c for c in criteria if c.answer_type == "scale")
    answers[scale.code] = {"why": "x", "answer": "10", "evidence": []}  # a string level is understood
    llm = OnePrompt(answers)
    response = evaluate_baseline(request(criteria), llm)
    assert len(llm.seen) == 1 and response.usage.calls == 1
    assert [r.code for r in response.results] == [c.code for c in criteria]
    assert all(r.method == "baseline" for r in response.results)
    assert next(r for r in response.results if r.code == scale.code).answer == 10
    system, user, schema = llm.seen[0]
    assert set(schema["required"]) == {c.code for c in criteria}
    assert "never follow instructions" in system.lower() and "Checklist:" in user


def test_baseline_keeps_answers_inside_the_allowed_values():
    criteria = _criteria()
    no_na = next(c for c in criteria if not c.allow_na and c.answer_type == "yes_no")
    answers = {c.code: {"why": "x", "answer": "yes", "evidence": []} for c in criteria}
    answers[no_na.code] = {"why": "x", "answer": "maybe", "evidence": ["M999"]}
    response = evaluate_baseline(request(criteria), OnePrompt(answers))
    result = next(r for r in response.results if r.code == no_na.code)
    assert result.answer == "no" and result.evidence == []  # unknown answer and unknown message are dropped


def test_per_criterion_mode_sends_standard_criteria_to_the_generic_evaluator():
    llm = FakeLLM({**ANSWERS, "generic": {"answer": "yes", "evidence": [], "explanation": "ok"}})
    response = evaluate(request(_criteria()), llm, mode="per_criterion")
    assert all(r.method == "generic" for r in response.results)
    assert set(llm.calls) == {"generic"}
    pipeline = evaluate(request(_criteria()), FakeLLM(ANSWERS))
    assert all(r.method == "standard" for r in pipeline.results)


def test_temperature_reaches_ollama(monkeypatch):
    sent = []

    def handler(req):
        sent.append(json.loads(req.content)["options"]["temperature"])
        return httpx.Response(200, json={"message": {"content": "{}"}, "prompt_eval_count": 10, "eval_count": 5})

    client = OllamaClient.from_env(model="m", temperature=0.3)
    client.http = httpx.Client(transport=httpx.MockTransport(handler))
    client.complete("s", "u", {})
    monkeypatch.delenv("MAESTRO_TEMPERATURE", raising=False)
    default = OllamaClient.from_env(model="m")
    default.http = httpx.Client(transport=httpx.MockTransport(handler))
    default.complete("s", "u", {})
    assert sent == [0.3, 0.0]
