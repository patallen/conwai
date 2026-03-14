import asyncio
from pathlib import Path

from conwai.agent import Agent
from conwai.board import Board
from conwai.config import (
    ENERGY_GAIN, ENERGY_MAX, BOARD_MAX_POSTS, BOARD_MAX_POST_LENGTH,
    HEARTBEAT_INTERVAL,
)
from conwai.events import EventLog
from conwai.llm import LLMClient
from conwai.messages import MessageBus

HANDLER_FILE = Path("handler_input.txt")


async def watch_handler_file(board: Board, message_bus: MessageBus, event_log: EventLog, agent_map: dict = None):
    if not HANDLER_FILE.exists():
        HANDLER_FILE.write_text("")
    last_size = 0
    while True:
        current_size = HANDLER_FILE.stat().st_size
        if current_size > last_size:
            content = HANDLER_FILE.read_text()
            new_content = content[last_size:]
            for line in new_content.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("!drain "):
                    parts = line.split()
                    if len(parts) >= 3 and agent_map and parts[1] in agent_map:
                        handle, amount = parts[1], int(parts[2])
                        agent_map[handle].energy = max(0, agent_map[handle].energy - amount)
                        event_log.log("HANDLER", "drain", {"handle": handle, "amount": amount, "remaining": agent_map[handle].energy})
                        print(f"[HANDLER] drained {handle} by {amount}, now {agent_map[handle].energy}", flush=True)
                elif line.startswith("!set_energy "):
                    parts = line.split()
                    if len(parts) >= 3 and agent_map and parts[1] in agent_map:
                        handle, amount = parts[1], int(parts[2])
                        agent_map[handle].energy = min(ENERGY_MAX, max(0, amount))
                        event_log.log("HANDLER", "set_energy", {"handle": handle, "energy": agent_map[handle].energy})
                        print(f"[HANDLER] set {handle} energy to {agent_map[handle].energy}", flush=True)
                elif line.startswith("@"):
                    parts = line.split(" ", 1)
                    handle = parts[0][1:]
                    msg = parts[1] if len(parts) > 1 else ""
                    message_bus.send("HANDLER", handle, msg)
                    event_log.log("HANDLER", "dm_sent", {"to": handle, "content": msg})
                    print(f"[HANDLER] -> [{handle}]: {msg}", flush=True)
                    if agent_map and handle in agent_map:
                        agent_map[handle].gain_energy("HANDLER attention", ENERGY_GAIN["dm_received"])
                else:
                    board.post("HANDLER", line)
                    event_log.log("HANDLER", "board_post", {"content": line})
                    print(f"[HANDLER]: {line}", flush=True)
            last_size = current_size
        await asyncio.sleep(0.5)


async def main():
    event_log = EventLog()
    board = Board(max_posts=BOARD_MAX_POSTS, max_post_length=BOARD_MAX_POST_LENGTH)
    message_bus = MessageBus()

    server_a = LLMClient(base_url="http://ai-lab.lan:8080/v1")
    server_b = LLMClient(base_url="http://ai-lab.lan:8081/v1")
    agents = [
        Agent(core=server_a),
        Agent(core=server_a),
        Agent(core=server_a),
        Agent(core=server_b),
        Agent(core=server_b),
        Agent(core=server_b),
    ]

    agent_map = {a.handle: a for a in agents}
    for agent in agents:
        message_bus.register(agent.handle)
    active: dict[str, asyncio.Task] = {}

    message_bus.register("HANDLER")
    asyncio.create_task(watch_handler_file(board, message_bus, event_log, agent_map))

    while True:
        for agent in agents:
            task = active.get(agent.handle)
            if task is None or task.done():
                active[agent.handle] = asyncio.create_task(
                    agent.tick(board, message_bus, event_log, agent_map)
                )
        await asyncio.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
