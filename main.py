import asyncio

from conwai.infra.logging import setup_logging
from scenarios.bread_economy.runner import run

if __name__ == "__main__":
    setup_logging()
    asyncio.run(run())
