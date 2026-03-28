import logging
import sys
from pathlib import Path

import structlog


def setup_logging(log_dir="data"):
    """Configure structlog: plain text to console, JSON lines to file."""
    Path(log_dir).mkdir(exist_ok=True)

    # File handler for JSON lines
    file_handler = logging.FileHandler(f"{log_dir}/sim.jsonl")
    file_handler.setLevel(logging.DEBUG)

    # Console handler for plain text
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # Configure stdlib logging (structlog routes through it)
    logging.basicConfig(
        format="%(message)s",
        level=logging.DEBUG,
        handlers=[console_handler, file_handler],
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Console: plain key=value rendering
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(),
    )
    console_handler.setFormatter(console_formatter)

    # File: JSON lines
    file_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
    )
    file_handler.setFormatter(file_formatter)
