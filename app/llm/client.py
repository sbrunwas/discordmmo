from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

from app.config import Settings
from app.db.store import Store

log = logging.getLogger(__name__)

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


class LLMClient:
    def __init__(self, settings: Settings, store: Store | None = None) -> None:
        self.settings = settings
        self.store = store
        self._memory_usage: dict[tuple[str, str], int] = {}

    @property
    def api_key(self) -> str | None:
        return self.settings.openrouter_api_key

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
        if self.settings.llm_backend != "openrouter":
            return self._stub(safe_prompt, response_format=response_format)
        if not self.settings.openrouter_api_key:
            log.warning("openrouter_missing_api_key fallback=stub")
            return self._stub(safe_prompt, response_format=response_format)
        if requests is None:
            log.warning("requests_not_available fallback=stub")
            return self._stub(safe_prompt, response_format=response_format)

        ok, reason = self._consume_budget(user_id)
        if not ok:
            msg = "LLM budget exhausted for today; using basic parser."
            log.warning("llm_budget_exhausted reason=%s", reason)
            return {"text": msg, "error": "budget_exhausted"}

        payload: dict[str, object] = {
            "model": self.settings.openrouter_model,
            "messages": self._messages(system_prompt, safe_prompt),
            "temperature": temperature,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        try:
            response = requests.post(
                f"{self.settings.openrouter_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost",
                    "X-Title": "discordmmo-dev",
                },
                data=json.dumps(payload),
                timeout=20,
            )
            if response.status_code == 404:
                detail = self._error_detail(response)
                log.warning("openrouter_http_404 fallback=stub detail=%s", detail)
                return {
                    "error": "openrouter_404",
                    "clarify_question": "OpenRouter request returned 404. Check OPENROUTER_MODEL and OPENROUTER_BASE_URL.",
                }
            if response.status_code in {401, 429} or response.status_code >= 500:
                log.warning("openrouter_http_error status=%s fallback=stub", response.status_code)
                return self._stub(safe_prompt, response_format=response_format)
            response.raise_for_status()
            parsed = response.json()
            content = parsed["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("unexpected_chat_content_type")
            if response_format and response_format.get("type") == "json_object":
                return self._parse_json_content(content)
            return {"text": content.strip()}
        except Exception:
            log.warning("openrouter_call_failed fallback=stub", exc_info=True)
            return self._stub(safe_prompt, response_format=response_format)

    def _messages(self, system_prompt: str | None, prompt: str) -> list[dict[str, str]]:
        if system_prompt:
            return [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]
        return [{"role": "user", "content": prompt}]

    def _stub(self, prompt: str, response_format: dict[str, str] | None = None) -> dict:
        log.info("llm_call backend=stub")
        if response_format and response_format.get("type") == "json_object":
            return {
                "action": "UNKNOWN",
                "target": None,
                "confidence": 0.0,
                "clarify_question": "LLM unavailable; using basic parser.",
            }
        return {"text": f"[stub] {prompt[:80]}"}

    def _error_detail(self, response) -> str:
        try:
            body = response.json()
            if isinstance(body, dict):
                err = body.get("error")
                if isinstance(err, dict):
                    message = err.get("message")
                    if isinstance(message, str):
                        return message[:200]
                return json.dumps(body)[:200]
        except Exception:
            pass
        return response.text[:200]

    def _parse_json_content(self, content: str) -> dict:
        body = content.strip()
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            # Some models wrap JSON in markdown code fences.
            match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", body, flags=re.DOTALL)
            if match:
                return json.loads(match.group(1))
            start = body.find("{")
            end = body.rfind("}")
            if start != -1 and end > start:
                return json.loads(body[start : end + 1])
            raise

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
