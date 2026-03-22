from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ActionFeedback:
    action: str
    args: dict[str, Any]
    result: str
