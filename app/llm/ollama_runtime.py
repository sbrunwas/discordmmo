from __future__ import annotations

import logging
import subprocess
import time

from app.config import Settings

log = logging.getLogger(__name__)

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


def is_ollama_healthy(settings: Settings) -> bool:
    if requests is None:
        return False
    try:
        response = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def ensure_ollama_running(settings: Settings) -> bool:
    if is_ollama_healthy(settings):
        return True

    try:
        subprocess.Popen(  # noqa: S603
            ["ollama", "serve"],
            stdout=None,
            stderr=None,
            start_new_session=True,
        )
    except FileNotFoundError:
        log.warning("ollama_binary_missing fallback=stub")
        return False
    except Exception:
        log.warning("ollama_start_failed fallback=stub", exc_info=True)
        return False

    deadline = time.time() + max(1, settings.ollama_start_timeout_seconds)
    while time.time() < deadline:
        if is_ollama_healthy(settings):
            log.info("ollama_ready base_url=%s", settings.ollama_base_url)
            return True
        time.sleep(0.5)

    log.warning("ollama_start_timeout timeout_seconds=%s fallback=stub", settings.ollama_start_timeout_seconds)
    return False
