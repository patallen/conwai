"""Context assembly: builds the LLM message list from board state."""

from __future__ import annotations

from typing import Any


class ContextAssembly:
    """Reads percept, identity, and recalled memories from the board and
    assembles a message snapshot ready for LLM inference."""

    def __init__(self, context_window: int = 10_000, system_prompt: str = ""):
        self.context_window = context_window
        self.system_prompt = system_prompt

    async def run(self, board: dict[str, Any]) -> None:
        state = board.setdefault("state", {})
        messages: list[dict] = state.setdefault("messages", [])
        percept = board.get("percept")

        tick = getattr(percept, "tick", 0)
        identity = getattr(percept, "identity", "")
        perception_text = getattr(percept, "to_prompt", lambda: "")()

        # Trim context window
        ctx_chars = sum(len(m.get("content", "")) for m in messages)
        while ctx_chars > self.context_window and len(messages) > 1:
            removed = messages.pop(0)
            ctx_chars -= len(removed.get("content", ""))

        # Identity slot (first message, updated each tick)
        if identity:
            if messages and messages[0].get("_identity"):
                messages[0] = {"role": "user", "content": identity, "_identity": True}
            else:
                messages.insert(0, {"role": "user", "content": identity, "_identity": True})

        # Recalled memories (ephemeral — included in snapshot only)
        recalled: list[str] = board.get("recalled", [])

        # Build the snapshot for inference (strip internal metadata keys)
        snapshot = [{k: v for k, v in m.items() if not k.startswith("_")} for m in messages]
        if recalled:
            recall_text = "=== RECALLED MEMORIES ===\n" + "\n".join(recalled) + "\n=== END ==="
            snapshot.append({"role": "user", "content": recall_text})

        # Perception
        snapshot.append({"role": "user", "content": perception_text})

        # Mark where this tick's messages start (for next tick's compression)
        messages.append({"role": "user", "content": perception_text})
        state["tick_msg_start"] = len(messages) - 1
        state["last_tick"] = tick

        board["messages_snapshot"] = snapshot
        board["system_prompt"] = self.system_prompt
