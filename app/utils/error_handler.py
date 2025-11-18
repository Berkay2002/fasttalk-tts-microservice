"""
Error handling utilities for the TTS service.

Borrowed from the patterns used by the other microservices to ensure a
consistent surface for orchestration and monitoring.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Callable, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Classification of failures to simplify downstream handling."""

    CONNECTION = "connection"
    PROCESSING = "processing"
    RESOURCE = "resource"
    CONFIGURATION = "configuration"
    SYSTEM = "system"
    TIMEOUT = "timeout"
    VALIDATION = "validation"


class ErrorSeverity(Enum):
    """Relative severity of errors."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ErrorInfo:
    """Structured metadata about an error occurrence."""

    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    recoverable: bool
    timestamp: float = field(default_factory=time.time)
    context: Dict[str, Any] = field(default_factory=dict)
    retry_after: Optional[float] = None


class TTSError(Exception):
    """Base exception used within the TTS service stack."""

    def __init__(
        self,
        message: str,
        *,
        category: ErrorCategory = ErrorCategory.SYSTEM,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        recoverable: bool = True,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.recoverable = recoverable
        self.retry_after = retry_after

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "recoverable": self.recoverable,
            "retry_after": self.retry_after,
        }


class CircuitBreakerState(Enum):
    """State machine for the circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Basic circuit breaker implementation to guard expensive operations
    like model initialisation or synthesis workloads.
    """

    def __init__(self, name: str, *, failure_threshold: int = 5, reset_timeout: float = 60.0) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout

        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure: Optional[float] = None
        self._lock = Lock()

    @property
    def state(self) -> CircuitBreakerState:
        with self._lock:
            self._maybe_reset()
            return self._state

    def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            self._maybe_reset()
            if self._state == CircuitBreakerState.OPEN:
                raise TTSError(
                    f"Circuit breaker '{self.name}' is OPEN",
                    category=ErrorCategory.RESOURCE,
                    severity=ErrorSeverity.HIGH,
                    recoverable=True,
                    retry_after=self.reset_timeout,
                )

        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            self._on_failure()
            raise
        else:
            self._on_success()
            return result

    def _on_success(self) -> None:
        with self._lock:
            if self._state in {CircuitBreakerState.OPEN, CircuitBreakerState.HALF_OPEN}:
                logger.info(f"Circuit breaker '{self.name}' closing after successful call")
            self._state = CircuitBreakerState.CLOSED
            self._failure_count = 0
            self._last_failure = None

    def _on_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure = time.time()

            if self._failure_count >= self.failure_threshold:
                if self._state != CircuitBreakerState.OPEN:
                    logger.warning(f"Circuit breaker '{self.name}' opening (failures={self._failure_count})")
                self._state = CircuitBreakerState.OPEN
            else:
                self._state = CircuitBreakerState.HALF_OPEN

    def _maybe_reset(self) -> None:
        if self._state == CircuitBreakerState.OPEN and self._last_failure is not None:
            if (time.time() - self._last_failure) >= self.reset_timeout:
                logger.info(f"Circuit breaker '{self.name}' transitioning to HALF_OPEN")
                self._state = CircuitBreakerState.HALF_OPEN


class ErrorTracker:
    """Rolling buffer capturing recent errors for diagnostics."""

    def __init__(self, max_entries: int = 100):
        self.max_entries = max_entries
        self._errors: Deque[ErrorInfo] = deque(maxlen=max_entries)
        self._lock = Lock()

    def add(self, info: ErrorInfo) -> None:
        with self._lock:
            self._errors.append(info)

    def recent(self, limit: int = 20) -> List[ErrorInfo]:
        with self._lock:
            return list(self._errors)[-limit:]

    def counts_by_category(self) -> Dict[str, int]:
        with self._lock:
            counts: Dict[str, int] = {}
            for err in self._errors:
                counts[err.category.value] = counts.get(err.category.value, 0) + 1
            return counts
