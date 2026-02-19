from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("DB_PATH", "mmo.db")
    dev_mode: bool = _env_bool("DEV_MODE", False)
    discord_token: str | None = os.getenv("DISCORD_TOKEN")
    rng_seed: int = int(os.getenv("RNG_SEED", "1337"))
    llm_backend: str = os.getenv("LLM_BACKEND", "stub").strip().lower()
    llm_json_backend: str = os.getenv("LLM_JSON_BACKEND", "openrouter").strip().lower()
    llm_text_backend: str = os.getenv("LLM_TEXT_BACKEND", "ollama").strip().lower()
    openrouter_api_key: str | None = os.getenv("OPENROUTER_API_KEY")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openrouter/auto:free")
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
    ollama_autostart: bool = _env_bool("OLLAMA_AUTOSTART", True)
    ollama_start_timeout_seconds: int = _env_int("OLLAMA_START_TIMEOUT_SECONDS", 20)
    llm_max_calls_per_day: int = _env_int("LLM_MAX_CALLS_PER_DAY", 50)
    llm_max_calls_per_user_per_day: int = _env_int("LLM_MAX_CALLS_PER_USER_PER_DAY", 10)
    llm_max_input_chars: int = _env_int("LLM_MAX_INPUT_CHARS", 600)

    @property
    def effective_llm_max_calls_per_day(self) -> int:
        return self.llm_max_calls_per_day * 5 if self.dev_mode else self.llm_max_calls_per_day

    @property
    def effective_llm_max_calls_per_user_per_day(self) -> int:
        return self.llm_max_calls_per_user_per_day * 5 if self.dev_mode else self.llm_max_calls_per_user_per_day

    def redacted(self) -> dict[str, object]:
        return {
            "db_path": self.db_path,
            "dev_mode": self.dev_mode,
            "discord_token_set": bool(self.discord_token),
            "rng_seed": self.rng_seed,
            "llm_backend": self.llm_backend,
            "llm_json_backend": self.llm_json_backend,
            "llm_text_backend": self.llm_text_backend,
            "openrouter_api_key_set": bool(self.openrouter_api_key),
            "openrouter_model": self.openrouter_model,
            "openrouter_base_url": self.openrouter_base_url,
            "ollama_base_url": self.ollama_base_url,
            "ollama_model": self.ollama_model,
            "ollama_autostart": self.ollama_autostart,
            "ollama_start_timeout_seconds": self.ollama_start_timeout_seconds,
            "llm_max_calls_per_day": self.effective_llm_max_calls_per_day,
            "llm_max_calls_per_user_per_day": self.effective_llm_max_calls_per_user_per_day,
            "llm_max_input_chars": self.llm_max_input_chars,
        }


def configure_logging(dev_mode: bool) -> None:
    level = logging.DEBUG if dev_mode else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
