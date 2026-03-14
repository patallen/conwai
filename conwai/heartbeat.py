from conwai.agent import Agent


class Heartbeat:
    def run(self, agents: list[Agent]):
        for agent in agents:
            if not agent.is_running():
                await agent.tick()