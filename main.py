import asyncio
from pathlib import Path

from conwai.agent import Agent, AgentCore
from conwai.board import Board
from conwai.events import EventLog
from conwai.messages import MessageBus

HANDLER_FILE = Path("handler_input.txt")


async def watch_handler_file(board: Board, message_bus: MessageBus, event_log: EventLog):
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
                if line.startswith("@"):
                    parts = line.split(" ", 1)
                    handle = parts[0][1:]
                    msg = parts[1] if len(parts) > 1 else ""
                    message_bus.send("HANDLER", handle, msg)
                    event_log.log("HANDLER", "dm_sent", {"to": handle, "content": msg})
                    print(f"[HANDLER] -> [{handle}]: {msg}", flush=True)
                else:
                    board.post("HANDLER", line)
                    event_log.log("HANDLER", "board_post", {"content": line})
                    print(f"[HANDLER]: {line}", flush=True)
            last_size = current_size
        await asyncio.sleep(0.5)


async def main():
    event_log = EventLog()
    board = Board()
    message_bus = MessageBus()
    server_a = AgentCore(base_url="http://ai-lab.lan:8080/v1")
    server_b = AgentCore(base_url="http://ai-lab.lan:8081/v1")
    agents = [
        Agent(core=server_a),
        Agent(core=server_a),
        Agent(core=server_a),
        Agent(core=server_b),
        Agent(core=server_b),
        Agent(core=server_b),
    ]
    for agent in agents:
        message_bus.register(agent.handle)
    active: dict[str, asyncio.Task] = {}

    message_bus.register("HANDLER")
    asyncio.create_task(watch_handler_file(board, message_bus, event_log))

    while True:
        for agent in agents:
            task = active.get(agent.handle)
            if task is None or task.done():
                active[agent.handle] = asyncio.create_task(agent.tick(board, message_bus, event_log))
        await asyncio.sleep(3.0)


if __name__ == "__main__":
    asyncio.run(main())
