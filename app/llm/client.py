from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    def complete_json(self, prompt: str) -> dict:
        log.info("llm_call stub=%s", self.api_key is None)
        return {"text": f"[stub] {prompt[:80]}"}
