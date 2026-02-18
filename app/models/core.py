from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ActionResult:
    ok: bool
    message: str
