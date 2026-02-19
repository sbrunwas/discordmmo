from __future__ import annotations

from app.config import Settings
from app.db.store import Store
from app.llm.client import LLMClient


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeRequests:
    def __init__(self) -> None:
        self.calls = 0

    def post(self, *args, **kwargs) -> FakeResponse:
        self.calls += 1
        return FakeResponse(
            200,
            {"choices": [{"message": {"content": "ok"}}]},
        )


class FakeRequests404:
    def post(self, *args, **kwargs) -> FakeResponse:
        return FakeResponse(404, {"error": {"message": "No route or model found"}})


class FakeRequestsPlainText:
    def post(self, *args, **kwargs) -> FakeResponse:
        return FakeResponse(200, {"choices": [{"message": {"content": "You see old star-metal under torchlight."}}]})


class FakeRequestsFencedJson:
    def post(self, *args, **kwargs) -> FakeResponse:
        return FakeResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": "```json\n{\"action\":\"LOOK\",\"target\":null,\"confidence\":0.9,\"clarify_question\":null}\n```"
                        }
                    }
                ]
            },
        )


def test_stub_backend_never_calls_network(monkeypatch):
    fake_requests = FakeRequests()
    monkeypatch.setattr("app.llm.client.requests", fake_requests)
    client = LLMClient(Settings(llm_json_backend="stub", llm_text_backend="stub"), store=None)

    result = client.complete_json("hello world", user_id="u1")

    assert fake_requests.calls == 0
    assert result["text"].startswith("[stub]")


def test_openrouter_missing_key_falls_back_to_stub_without_network(monkeypatch):
    fake_requests = FakeRequests()
    monkeypatch.setattr("app.llm.client.requests", fake_requests)
    client = LLMClient(Settings(llm_json_backend="openrouter", llm_text_backend="stub", openrouter_api_key=None), store=None)

    result = client.complete_json("hello world", user_id="u1")

    assert fake_requests.calls == 0
    assert result["text"].startswith("[stub]")


def test_openrouter_without_requests_returns_intent_fallback_json(monkeypatch):
    monkeypatch.setattr("app.llm.client.requests", None)
    client = LLMClient(Settings(llm_json_backend="openrouter", llm_text_backend="openrouter", openrouter_api_key="test-key"), store=None)

    result = client.complete_json("what happens now", user_id="u1", response_format={"type": "json_object"})

    assert result["action"] == "UNKNOWN"
    assert result["clarify_question"] == "LLM unavailable; using basic parser."


def test_openrouter_daily_limits_block_after_quota(monkeypatch, tmp_path):
    fake_requests = FakeRequests()
    monkeypatch.setattr("app.llm.client.requests", fake_requests)
    settings = Settings(
        llm_json_backend="openrouter",
        llm_text_backend="openrouter",
        openrouter_api_key="test-key",
        llm_max_calls_per_day=1,
        llm_max_calls_per_user_per_day=1,
        dev_mode=False,
    )
    store = Store(str(tmp_path / "limits.db"))
    client = LLMClient(settings, store=store)

    first = client.complete_json("first", user_id="u1")
    second = client.complete_json("second", user_id="u1")

    assert first["text"] == "ok"
    assert second["error"] == "budget_exhausted"
    assert fake_requests.calls == 1


def test_openrouter_404_returns_model_hint(monkeypatch):
    monkeypatch.setattr("app.llm.client.requests", FakeRequests404())
    client = LLMClient(Settings(llm_json_backend="openrouter", llm_text_backend="openrouter", openrouter_api_key="test-key"), store=None)

    result = client.complete_json("hi", user_id="u1", response_format={"type": "json_object"})

    assert result["error"] == "openrouter_404"


def test_openrouter_plain_text_is_returned_for_non_json_requests(monkeypatch):
    monkeypatch.setattr("app.llm.client.requests", FakeRequestsPlainText())
    client = LLMClient(Settings(llm_json_backend="openrouter", llm_text_backend="openrouter", openrouter_api_key="test-key"), store=None)

    result = client.complete_json("narrate this", user_id="u1")

    assert result["text"] == "You see old star-metal under torchlight."


def test_openrouter_fenced_json_is_parsed_for_json_requests(monkeypatch):
    monkeypatch.setattr("app.llm.client.requests", FakeRequestsFencedJson())
    client = LLMClient(Settings(llm_json_backend="openrouter", llm_text_backend="openrouter", openrouter_api_key="test-key"), store=None)

    result = client.complete_json("intent please", user_id="u1", response_format={"type": "json_object"})

    assert result["action"] == "LOOK"
