from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from conwai.bulletin_board import BulletinBoard
from conwai.config import BOARD_MAX_POSTS, BOARD_MAX_POST_LENGTH
from conwai.events import EventLog
from conwai.messages import MessageBus

if TYPE_CHECKING:
    from conwai.pool import AgentPool
    from conwai.world import WorldEvents


@dataclass
class Context:
    board: BulletinBoard = field(
        default_factory=lambda: BulletinBoard(
            max_posts=BOARD_MAX_POSTS, max_post_length=BOARD_MAX_POST_LENGTH
        )
    )
    bus: MessageBus = field(default_factory=MessageBus)
    events: EventLog = field(default_factory=EventLog)
    pool: AgentPool | None = field(default=None, repr=False)
    world: WorldEvents | None = field(default=None, repr=False)
    tick: int = 0

    def log(self, handle: str, event_type: str, data: dict | None = None):
        self.events.log(handle, event_type, data)

