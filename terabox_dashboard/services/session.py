"""Server-side session store dengan TTL & background cleanup."""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .terabox import TeraBoxClient
    from ..config import Settings


@dataclass(slots=True)
class _SessionEntry:
    client: "TeraBoxClient"
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)


class SessionStore:
    """Thread-safe in-memory session store dengan TTL."""

    def __init__(self, ttl_seconds: int = 86400, cleanup_interval: int = 3600) -> None:
        self._store: dict[str, _SessionEntry] = {}
        self._lock = threading.RLock()
        self._ttl = ttl_seconds
        self._cleanup_interval = cleanup_interval
        self._cleanup_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def create(self, client: "TeraBoxClient") -> str:
        """Simpan client, return session ID."""
        sid = secrets.token_urlsafe(24)
        with self._lock:
            self._store[sid] = _SessionEntry(client=client)
        return sid

    def get(self, sid: str) -> "TeraBoxClient | None":
        """Ambil client & refresh accessed_at. Return None jika expired/tidak ada."""
        with self._lock:
            entry = self._store.get(sid)
            if not entry:
                return None
            if time.time() - entry.created_at > self._ttl:
                del self._store[sid]
                return None
            entry.accessed_at = time.time()
            return entry.client

    def delete(self, sid: str) -> None:
        """Hapus session."""
        with self._lock:
            self._store.pop(sid, None)

    def _cleanup_expired(self) -> None:
        """Hapus session yang expired."""
        now = time.time()
        with self._lock:
            expired = [
                sid for sid, e in self._store.items()
                if now - e.created_at > self._ttl
            ]
            for sid in expired:
                del self._store[sid]

    def _cleanup_loop(self) -> None:
        while not self._stop_event.wait(self._cleanup_interval):
            self._cleanup_expired()

    def start_background_cleanup(self) -> None:
        """Mulai background cleanup thread (daemon)."""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            return
        self._stop_event.clear()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def stop_background_cleanup(self) -> None:
        """Hentikan background cleanup thread."""
        self._stop_event.set()
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
            self._cleanup_thread = None


# Global instance (diinisialisasi di app factory)
_session_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _session_store
    if _session_store is None:
        from ..config import SETTINGS
        _session_store = SessionStore(
            ttl_seconds=3600 if SETTINGS.session_cookie_secure else 86400,
            cleanup_interval=3600,
        )
    return _session_store


def init_session_store(settings: "Settings") -> SessionStore:
    """Dipanggil sekali di create_app()."""
    global _session_store
    _session_store = SessionStore(
        ttl_seconds=86400,
        cleanup_interval=3600,
    )
    return _session_store
