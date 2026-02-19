from __future__ import annotations

from app.config import Settings
from app.llm.client import LLMClient
from app.llm.intent_parser import parse_intent
from app.llm.narrator import narrate_outcome
from app.llm.ollama_runtime import ensure_ollama_running
from app.main import main
from app.models.core import EngineOutcome


class FakeHybridResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeHybridRequests:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def post(self, url: str, *args, **kwargs) -> FakeHybridResponse:
        self.urls.append(url)
        if url.endswith("/chat/completions"):
            return FakeHybridResponse(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"action":"HELP","target":null,"confidence":0.9,"clarify_question":null}'
                            }
                        }
                    ]
                },
            )
        if url.endswith("/api/chat"):
            return FakeHybridResponse(200, {"message": {"content": "A quiet wind carries ash through the stones."}})
        raise AssertionError(f"unexpected url {url}")


def test_hybrid_routing_uses_openrouter_for_intent_and_ollama_for_narration(monkeypatch):
    fake_requests = FakeHybridRequests()
    monkeypatch.setattr("app.llm.client.requests", fake_requests)
    settings = Settings(
        llm_json_backend="openrouter",
        llm_text_backend="ollama",
        openrouter_api_key="test-key",
    )
    client = LLMClient(settings, store=None)

    intent = parse_intent("what can you do", llm_client=client)
    narration = narrate_outcome(
        client,
        outcome=EngineOutcome(
            action="LOOK",
            result="moved",
            roll=None,
            hp_delta=0,
            xp_delta=0,
            location_id="town_square",
            npc_name=None,
            npc_reply=None,
            is_scene_description=False,
        ),
        location_name="Asterfall Commons",
        location_description="Stone alleys and hanging banners.",
        recent_events=[],
        last_npc_exchange="",
        last_narration="",
        session_state={"mode": "explore"},
        user_id="u1",
    )

    assert intent.action == "HELP"
    assert narration == "A quiet wind carries ash through the stones."
    assert any(url.endswith("/chat/completions") for url in fake_requests.urls)
    assert any(url.endswith("/api/chat") for url in fake_requests.urls)


def test_missing_openrouter_key_falls_back_in_intent_parser():
    client = LLMClient(
        Settings(
            llm_json_backend="openrouter",
            llm_text_backend="stub",
            openrouter_api_key=None,
        ),
        store=None,
    )
    intent = parse_intent("what can you do", llm_client=client)
    assert intent.action == "UNKNOWN"
    assert intent.clarify_question == "LLM unavailable; using basic parser."


def test_main_falls_back_to_stub_text_backend_when_ollama_autostart_fails(monkeypatch):
    settings = Settings(
        discord_token="test-token",
        llm_json_backend="stub",
        llm_text_backend="ollama",
        ollama_autostart=True,
    )
    seen: dict[str, object] = {}

    monkeypatch.setattr("app.main.Settings", lambda: settings)
    monkeypatch.setattr("app.main.configure_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.main.ensure_ollama_running", lambda *_args, **_kwargs: False)
    monkeypatch.setattr("app.main.build_engine", lambda _settings: object())

    def _run_discord_bot(_engine, runtime_settings):
        seen["backend"] = runtime_settings.llm_text_backend

    monkeypatch.setattr("app.main.run_discord_bot", _run_discord_bot)
    main()

    assert seen["backend"] == "stub"


def test_ollama_autostart_returns_false_when_unavailable(monkeypatch):
    class DownRequests:
        def get(self, *args, **kwargs):
            raise RuntimeError("down")

    monkeypatch.setattr("app.llm.ollama_runtime.requests", DownRequests())

    def _missing_binary(*args, **kwargs):
        raise FileNotFoundError("ollama")

    monkeypatch.setattr("app.llm.ollama_runtime.subprocess.Popen", _missing_binary)

    ok = ensure_ollama_running(
        Settings(
            llm_json_backend="stub",
            llm_text_backend="ollama",
            ollama_autostart=True,
        )
    )
    assert ok is False
