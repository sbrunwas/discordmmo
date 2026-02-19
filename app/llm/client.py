from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.db.store import Store

log = logging.getLogger(__name__)

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


class ProviderUnavailableError(RuntimeError):
    pass


class OpenRouter404Error(RuntimeError):
    pass


class LLMIntentJSON(BaseModel):
    action: Literal[
        "LOOK",
        "MOVE",
        "INVESTIGATE",
        "TALK",
        "REST_SHORT",
        "REST_LONG",
        "HELP",
        "START",
        "STATS",
        "INVENTORY",
        "SKILLS",
        "RESPEC",
        "FACTIONS",
        "RECAP",
        "DUEL",
        "UNKNOWN",
    ]
    target: str | None = None
    confidence: float = 0.0
    clarify_question: str | None = None


class BaseProvider(ABC):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.max_input_chars = settings.llm_max_input_chars

    def _truncate(self, text: str) -> str:
        return text[: self.max_input_chars]

    @abstractmethod
    def generate_json(
        self,
        system_prompt: str | None,
        user_prompt: str,
        *,
        temperature: float = 0.0,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_text(
        self,
        system_prompt: str | None,
        user_prompt: str,
        *,
        temperature: float = 0.7,
    ) -> str:
        raise NotImplementedError


class StubProvider(BaseProvider):
    def generate_json(
        self,
        system_prompt: str | None,
        user_prompt: str,
        *,
        temperature: float = 0.0,
    ) -> str:
        del system_prompt, temperature
        payload = {
            "action": "UNKNOWN",
            "target": None,
            "confidence": 0.0,
            "clarify_question": "LLM unavailable; using basic parser.",
        }
        return json.dumps(payload, sort_keys=True)

    def generate_text(
        self,
        system_prompt: str | None,
        user_prompt: str,
        *,
        temperature: float = 0.7,
    ) -> str:
        del system_prompt, temperature
        return f"[stub] {self._truncate(user_prompt)[:80]}"


class OpenRouterProvider(BaseProvider):
    def _messages(self, system_prompt: str | None, user_prompt: str) -> list[dict[str, str]]:
        safe_prompt = self._truncate(user_prompt)
        if system_prompt:
            return [
                {"role": "system", "content": self._truncate(system_prompt)},
                {"role": "user", "content": safe_prompt},
            ]
        return [{"role": "user", "content": safe_prompt}]

    def _headers(self) -> dict[str, str]:
        api_key = self.settings.openrouter_api_key
        if not api_key:
            raise ProviderUnavailableError("openrouter_missing_api_key")
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "discordmmo-dev",
        }

    def _extract_content(self, response) -> str:
        parsed = response.json()
        content = parsed["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ProviderUnavailableError("unexpected_chat_content_type")
        return content.strip()

    def _post_chat(
        self,
        system_prompt: str | None,
        user_prompt: str,
        *,
        temperature: float,
        response_format: dict[str, str] | None = None,
    ) -> str:
        if requests is None:
            raise ProviderUnavailableError("requests_unavailable")
        payload: dict[str, object] = {
            "model": self.settings.openrouter_model,
            "messages": self._messages(system_prompt, user_prompt),
            "temperature": temperature,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        response = requests.post(
            f"{self.settings.openrouter_base_url}/chat/completions",
            headers=self._headers(),
            data=json.dumps(payload),
            timeout=20,
        )
        if response.status_code == 404:
            raise OpenRouter404Error("OpenRouter request returned 404. Check OPENROUTER_MODEL and OPENROUTER_BASE_URL.")
        if response.status_code in {401, 429} or response.status_code >= 500:
            raise ProviderUnavailableError(f"openrouter_http_{response.status_code}")
        response.raise_for_status()
        return self._extract_content(response)

    def generate_json(
        self,
        system_prompt: str | None,
        user_prompt: str,
        *,
        temperature: float = 0.0,
    ) -> str:
        return self._post_chat(
            system_prompt,
            user_prompt,
            temperature=temperature,
            response_format={"type": "json_object"},
        )

    def generate_text(
        self,
        system_prompt: str | None,
        user_prompt: str,
        *,
        temperature: float = 0.7,
    ) -> str:
        return self._post_chat(system_prompt, user_prompt, temperature=temperature, response_format=None)


class OllamaProvider(BaseProvider):
    def _chat(
        self,
        system_prompt: str | None,
        user_prompt: str,
        *,
        temperature: float,
    ) -> str:
        if requests is None:
            raise ProviderUnavailableError("requests_unavailable")

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": self._truncate(system_prompt)})
        messages.append({"role": "user", "content": self._truncate(user_prompt)})
        payload = {
            "model": self.settings.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        response = requests.post(
            f"{self.settings.ollama_base_url}/api/chat",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=20,
        )
        response.raise_for_status()
        body = response.json()
        message = body.get("message", {})
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise ProviderUnavailableError("ollama_unexpected_response")
        return content.strip()

    def generate_json(
        self,
        system_prompt: str | None,
        user_prompt: str,
        *,
        temperature: float = 0.0,
    ) -> str:
        return self._chat(system_prompt, user_prompt, temperature=temperature)

    def generate_text(
        self,
        system_prompt: str | None,
        user_prompt: str,
        *,
        temperature: float = 0.7,
    ) -> str:
        return self._chat(system_prompt, user_prompt, temperature=temperature)


class LLMClient:
    def __init__(self, settings: Settings, store: Store | None = None) -> None:
        self.settings = settings
        self.store = store
        self._memory_usage: dict[tuple[str, str], int] = {}
        self._stub = StubProvider(settings)
        self._providers: dict[str, BaseProvider] = {
            "stub": self._stub,
            "openrouter": OpenRouterProvider(settings),
            "ollama": OllamaProvider(settings),
        }

    def complete_json(
        self,
        prompt: str,
        user_id: str = "system",
        *,
        system_prompt: str | None = None,
        response_format: dict[str, str] | None = None,
        temperature: float = 0.2,
    ) -> dict:
        safe_prompt = prompt[: self.settings.llm_max_input_chars]

        if response_format and response_format.get("type") == "json_object":
            backend = self._select_backend(self.settings.llm_json_backend, legacy_fallback=self.settings.llm_backend)
            provider = self._providers[backend]
            if backend == "openrouter":
                ok, reason = self._consume_budget(user_id)
                if not ok:
                    log.warning("llm_budget_exhausted reason=%s", reason)
                    return {"text": "LLM budget exhausted for today; using basic parser.", "error": "budget_exhausted"}
            try:
                raw = provider.generate_json(system_prompt, safe_prompt, temperature=temperature)
                data = self._parse_json_content(raw)
                validated = LLMIntentJSON(**data)
                return validated.model_dump()
            except OpenRouter404Error as exc:
                log.warning("openrouter_http_404 fallback=stub detail=%s", str(exc))
                return {
                    "error": "openrouter_404",
                    "clarify_question": "OpenRouter request returned 404. Check OPENROUTER_MODEL and OPENROUTER_BASE_URL.",
                }
            except (ValidationError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                log.warning("intent_json_validation_failed fallback=stub", exc_info=True)
                return self._stub_json_dict()
            except Exception:
                log.warning("json_provider_failed backend=%s fallback=stub", backend, exc_info=True)
                return self._stub_json_dict()

        backend = self._select_backend(self.settings.llm_text_backend, legacy_fallback=self.settings.llm_backend)
        provider = self._providers[backend]
        if backend == "openrouter":
            ok, reason = self._consume_budget(user_id)
            if not ok:
                log.warning("llm_budget_exhausted reason=%s", reason)
                return {"text": "LLM budget exhausted for today; using basic parser.", "error": "budget_exhausted"}
        try:
            text = provider.generate_text(system_prompt, safe_prompt, temperature=temperature).strip()
            if text:
                return {"text": text}
            return {"text": self._stub.generate_text(system_prompt, safe_prompt, temperature=temperature)}
        except Exception:
            log.warning("text_provider_failed backend=%s fallback=stub", backend, exc_info=True)
            return {"text": self._stub.generate_text(system_prompt, safe_prompt, temperature=temperature)}

    def _select_backend(self, backend: str, *, legacy_fallback: str) -> str:
        normalized = (backend or "").strip().lower()
        if normalized in self._providers:
            return normalized
        legacy = (legacy_fallback or "").strip().lower()
        if legacy in self._providers:
            return legacy
        return "stub"

    def _stub_json_dict(self) -> dict:
        return {
            "action": "UNKNOWN",
            "target": None,
            "confidence": 0.0,
            "clarify_question": "LLM unavailable; using basic parser.",
        }

    def _parse_json_content(self, content: str) -> dict:
        body = content.strip()
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", body, flags=re.DOTALL)
        if match:
            return json.loads(match.group(1))
        start = body.find("{")
        end = body.rfind("}")
        if start != -1 and end > start:
            return json.loads(body[start : end + 1])
        raise json.JSONDecodeError("no_json_object", body, 0)

    def _consume_budget(self, user_id: str) -> tuple[bool, str | None]:
        day = datetime.now(UTC).date().isoformat()
        max_day = self.settings.effective_llm_max_calls_per_day
        max_user = self.settings.effective_llm_max_calls_per_user_per_day
        if self.store is not None:
            return self.store.try_consume_llm_call(
                day=day,
                user_id=user_id,
                max_calls_per_day=max_day,
                max_calls_per_user_per_day=max_user,
            )

        global_calls = sum(count for (d, _), count in self._memory_usage.items() if d == day)
        user_calls = self._memory_usage.get((day, user_id), 0)
        if global_calls >= max_day:
            return False, "global_limit"
        if user_calls >= max_user:
            return False, "user_limit"
        self._memory_usage[(day, user_id)] = user_calls + 1
        return True, None
