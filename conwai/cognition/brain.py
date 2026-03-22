from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Decision:
    action: str
    args: dict[str, Any] = field(default_factory=dict)
