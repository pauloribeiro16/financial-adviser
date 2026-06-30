import os
import sys

import structlog


def setup_logging(service: str = "mi") -> None:
    env = os.getenv("MFL_ENV", "production")
    processors = [
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
    ]
    if env == "development":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        cache_logger_on_first_use=True,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger | structlog.BoundLogger:
    return structlog.get_logger(name)
