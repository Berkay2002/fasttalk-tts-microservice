"""
Structured logging utilities for the TTS service.

Provides JSON-formatted logs for aggregation alongside a readable console
formatter, matching the conventions established in the other microservices.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Dict, Iterator, Optional

REQUEST_ID: ContextVar[Optional[str]] = ContextVar("tts_request_id", default=None)


class JsonFormatter(logging.Formatter):
    """Emit structured log records as JSON for log aggregation pipelines."""

    def format(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, dict):
            payload = record.msg.copy()
        else:
            payload = {
                "message": record.getMessage(),
            }

        payload.update(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "service": "tts-service",
                "logger": record.name,
            }
        )

        request_id = REQUEST_ID.get()
        if request_id:
            payload.setdefault("request_id", request_id)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)

        return json.dumps(payload)


class ConsoleFormatter(logging.Formatter):
    """Human friendly console output with lightweight colouring."""

    _COLOURS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
        "RESET": "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        colour = self._COLOURS.get(record.levelname, self._COLOURS["RESET"])
        reset = self._COLOURS["RESET"]
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        level = f"{colour}{record.levelname:8s}{reset}"
        logger_name = f"{record.name:30s}"
        message = record.getMessage()

        request_id = REQUEST_ID.get()
        if request_id:
            message = f"[{request_id[:8]}] {message}"

        formatted = f"{timestamp} | {level} | {logger_name} | {message}"

        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)

        return formatted


class StructuredLogger:
    """
    Wrapper around the standard logging module to provide convenience helpers
    and request-scoped context, similar to the STT/LLM services.
    """

    def __init__(
        self,
        name: str,
        log_level: str = "INFO",
        logfile: Optional[str] = None,
        enable_console: bool = True,
        enable_file: bool = True,
    ) -> None:
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        self.logger.handlers.clear()

        if enable_console:
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setFormatter(ConsoleFormatter())
            self.logger.addHandler(stream_handler)

        if enable_file and logfile:
            file_handler = logging.FileHandler(logfile)
            file_handler.setFormatter(JsonFormatter())
            self.logger.addHandler(file_handler)

        self.logger.propagate = False

    # ----------------------------------------------------------------- contexts
    @contextmanager
    def request_context(self, request_id: Optional[str] = None) -> Iterator[str]:
        """Context manager that sets a request id for correlated logging."""
        token = REQUEST_ID.set(request_id or uuid.uuid4().hex)
        try:
            yield REQUEST_ID.get() or ""
        finally:
            REQUEST_ID.reset(token)

    # ----------------------------------------------------------------- logging
    def _handle(self, level: int, message: str, **extra: Any) -> None:
        record = self.logger.makeRecord(
            name=self.logger.name,
            level=level,
            fn="",
            lno=0,
            msg=message,
            args=(),
            exc_info=extra.pop("exc_info", None),
        )
        if extra:
            record.extra_fields = extra
        self.logger.handle(record)

    def debug(self, message: str, **extra: Any) -> None:
        self._handle(logging.DEBUG, message, **extra)

    def info(self, message: str, **extra: Any) -> None:
        self._handle(logging.INFO, message, **extra)

    def warning(self, message: str, **extra: Any) -> None:
        self._handle(logging.WARNING, message, **extra)

    def error(self, message: str, **extra: Any) -> None:
        exc_info = extra.pop("exc_info", None)
        self._handle(logging.ERROR, message, exc_info=exc_info, **extra)

    def critical(self, message: str, **extra: Any) -> None:
        self._handle(logging.CRITICAL, message, **extra)


_GLOBAL_LOGGER: Optional[StructuredLogger] = None


def get_logger(name: str = "tts-service") -> StructuredLogger:
    """
    Obtain a structured logger instance.

    Lazily initialises a global logger the first time it is requested so other
    modules can reuse the same handler configuration.
    """
    global _GLOBAL_LOGGER
    if _GLOBAL_LOGGER is None:
        _GLOBAL_LOGGER = StructuredLogger(name="tts-service")
    if name == "tts-service":
        return _GLOBAL_LOGGER
    return StructuredLogger(name)


def log_execution_time(logger: StructuredLogger):
    """Decorator to log execution durations for diagnostic purposes."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.time() - start
                logger.debug(f"{func.__name__} completed", duration_seconds=round(duration, 4))

        return wrapper

    return decorator
