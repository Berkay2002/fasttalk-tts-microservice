"""
WebSocket connection management utilities for the TTS service.

The implementation mirrors the approach used in the other microservices so the
backend orchestration layer can introspect connection metrics consistently.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Dict, Optional


class ConnectionState(Enum):
    """Connection lifecycle states."""

    CONNECTING = "connecting"
    ACTIVE = "active"
    PROCESSING = "processing"
    CLOSED = "closed"


@dataclass
class ConnectionInfo:
    """Metadata about a WebSocket connection."""

    session_id: str
    client: Optional[str] = None
    state: ConnectionState = ConnectionState.CONNECTING
    start_time: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    messages_received: int = 0
    messages_sent: int = 0
    characters_synthesised: int = 0
    errors: int = 0

    metadata: Dict[str, Any] = field(default_factory=dict)

    def mark_active(self) -> None:
        self.state = ConnectionState.ACTIVE
        self.last_activity = time.time()

    def mark_processing(self) -> None:
        self.state = ConnectionState.PROCESSING
        self.last_activity = time.time()

    def mark_closed(self) -> None:
        self.state = ConnectionState.CLOSED
        self.last_activity = time.time()

    def duration(self) -> float:
        return time.time() - self.start_time

    def idle_time(self) -> float:
        return time.time() - self.last_activity


class ConnectionManager:
    """Thread-safe tracker for WebSocket connections."""

    def __init__(self, max_connections: int = 50):
        self.max_connections = max_connections
        self._connections: Dict[str, ConnectionInfo] = {}
        self._lock = Lock()

        # Aggregate metrics
        self.total_connections = 0
        self.total_disconnections = 0
        self.total_messages_received = 0
        self.total_messages_sent = 0
        self.total_characters = 0
        self.total_errors = 0

    # ----------------------------------------------------------------- lifecycle
    def add_connection(self, session_id: str, client: Optional[str] = None) -> Optional[ConnectionInfo]:
        with self._lock:
            if len(self._connections) >= self.max_connections:
                return None

            info = ConnectionInfo(session_id=session_id, client=client)
            info.mark_active()
            self._connections[session_id] = info
            self.total_connections += 1
            return info

    def remove_connection(self, session_id: str) -> Optional[ConnectionInfo]:
        with self._lock:
            info = self._connections.pop(session_id, None)
            if info:
                info.mark_closed()
                self.total_disconnections += 1
                self.total_messages_received += info.messages_received
                self.total_messages_sent += info.messages_sent
                self.total_characters += info.characters_synthesised
                self.total_errors += info.errors
            return info

    def get(self, session_id: str) -> Optional[ConnectionInfo]:
        with self._lock:
            return self._connections.get(session_id)

    def active_count(self) -> int:
        with self._lock:
            return len(self._connections)

    def snapshot(self) -> Dict[str, Any]:
        """Return a snapshot suitable for diagnostics/monitoring."""
        with self._lock:
            return {
                "active_connections": len(self._connections),
                "max_connections": self.max_connections,
                "total_connections": self.total_connections,
                "total_disconnections": self.total_disconnections,
                "total_messages_received": self.total_messages_received,
                "total_messages_sent": self.total_messages_sent,
                "total_characters": self.total_characters,
                "total_errors": self.total_errors,
            }

    # ----------------------------------------------------------------- metrics
    def record_message_received(self, session_id: str) -> None:
        info = self.get(session_id)
        if info:
            info.messages_received += 1
            info.last_activity = time.time()

    def record_message_sent(self, session_id: str) -> None:
        info = self.get(session_id)
        if info:
            info.messages_sent += 1
            info.last_activity = time.time()

    def record_characters(self, session_id: str, characters: int) -> None:
        info = self.get(session_id)
        if info:
            info.characters_synthesised += characters

    def record_error(self, session_id: str) -> None:
        info = self.get(session_id)
        if info:
            info.errors += 1
            info.last_activity = time.time()
