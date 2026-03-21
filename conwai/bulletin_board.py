from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.storage import Storage


@dataclass
class Post:
    handle: str
    content: str
    timestamp: float = field(default_factory=time)


class BulletinBoard:
    def __init__(
        self,
        max_posts: int = 30,
        max_post_length: int = 200,
        storage: Storage | None = None,
        entity: str = "WORLD",
        component: str = "board",
    ):
        self.max_posts = max_posts
        self.max_post_length = max_post_length
        self._posts: list[Post] = []
        self._cursors: dict[str, int] = {}
        self._storage = storage
        self._entity = entity
        self._component = component
        self._load()

    def _load(self):
        if not self._storage:
            return
        data = self._storage.load_component(self._entity, self._component)
        if data:
            self._posts = [Post(**p) for p in data.get("posts", [])]
            self._cursors = data.get("cursors", {})

    def _save(self):
        if not self._storage:
            return
        self._storage.save_component(self._entity, self._component, {
            "posts": [{"handle": p.handle, "content": p.content, "timestamp": p.timestamp} for p in self._posts],
            "cursors": self._cursors,
        })

    def post(self, handle: str, content: str):
        content = content[: self.max_post_length]
        self._posts.append(Post(handle=handle, content=content))
        if len(self._posts) > self.max_posts:
            overflow = len(self._posts) - self.max_posts
            self._posts = self._posts[-self.max_posts :]
            for h in self._cursors:
                self._cursors[h] = max(0, self._cursors[h] - overflow)
        self._save()

    def read_new(self, handle: str) -> list[Post]:
        cursor = self._cursors.get(handle, 0)
        new_posts = self._posts[cursor:]
        self._cursors[handle] = len(self._posts)
        self._save()  # persist cursor update
        return new_posts

    def recent_by_handle(self, handle: str, n: int = 10) -> list[Post]:
        """Return the last n posts by a specific handle."""
        return [p for p in self._posts[-n:] if p.handle == handle]
