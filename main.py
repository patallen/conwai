import asyncio
import sys

from conwai.infra.logging import setup_logging

if __name__ == "__main__":
    setup_logging()
    scenario = sys.argv[1] if len(sys.argv) > 1 else "bread_economy"
    if scenario == "commons":
        from scenarios.commons.runner import run
    else:
        from scenarios.bread_economy.runner import run
    asyncio.run(run())
