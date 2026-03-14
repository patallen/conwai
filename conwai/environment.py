from dataclasses import dataclass, field

from conwai.board import Board
from conwai.config import BOARD_MAX_POSTS, BOARD_MAX_POST_LENGTH
from conwai.events import EventLog
from conwai.messages import MessageBus


@dataclass
class Context:
    board: Board = field(
        default_factory=lambda: Board(
            max_posts=BOARD_MAX_POSTS, max_post_length=BOARD_MAX_POST_LENGTH
        )
    )
    bus: MessageBus = field(default_factory=MessageBus)
    events: EventLog = field(default_factory=EventLog)
    agent_map: dict = field(default_factory=dict)
    tick: int = 0

    def log(self, handle: str, event_type: str, data: dict | None = None):
        self.events.log(handle, event_type, data)

    def register_agent(self, agent):
        self.agent_map[agent.handle] = agent
        self.bus.register(agent.handle)
