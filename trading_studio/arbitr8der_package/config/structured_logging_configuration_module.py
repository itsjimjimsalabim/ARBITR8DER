"""Structured logging configuration for the trading studio.

Provides JSON-structured logs to stdout and a rotating file log under runtime/logs/.
"""

import logging
import logging.handlers
import sys

from arbitr8der_package.config.cwd_independent_path_resolver import RUNTIME_LOGS_DIR, ensure_runtime_dirs

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_JSON_LOG_FORMAT = '{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'


def configure_structured_logging(level: int = logging.INFO) -> None:
    """Set up root logger with console and file handlers."""
    ensure_runtime_dirs()

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if root_logger.handlers:
        return

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root_logger.addHandler(console_handler)

    # File handler — rotating, 5MB, keep 3 backups
    log_file = RUNTIME_LOGS_DIR / "arbitr8der.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger. Configures logging if not already set up."""
    configure_structured_logging()
    return logging.getLogger(name)
