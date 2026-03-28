import logging
import sys
from pathlib import Path


def setup_logging(log_dir="data"):
    log = logging.getLogger("conwai")
    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
    log.setLevel(logging.INFO)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    log.addHandler(console)

    Path(log_dir).mkdir(exist_ok=True)
    fh = logging.FileHandler(f"{log_dir}/sim.log")
    fh.setFormatter(fmt)
    log.addHandler(fh)
