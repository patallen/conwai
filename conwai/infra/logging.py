import logging
import sys
from pathlib import Path

from main import log


def setup_logging():
    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
    log.setLevel(logging.INFO)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    log.addHandler(console)

    Path("data").mkdir(exist_ok=True)
    fh = logging.FileHandler("data/sim.log")
    fh.setFormatter(fmt)
    log.addHandler(fh)
