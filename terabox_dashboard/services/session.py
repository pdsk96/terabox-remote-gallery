"""Server-side session store dengan TTL, persistensi disk & background cleanup."""
from __future__ import annotations

import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
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
    """Thread-safe session store dengan TTL dan persistensi ke file JSON.

    Session dipersistenkan agar login tidak hilang saat server di-restart.
    Yang disimpan hanya cookie `ndus` (bukan objek client), lalu client
    dibangun ulang saat process start.
    """

    def __init__(
        self,
        ttl_seconds: int = 86400,
        cleanup_interval: int = 3600,
        persist_path: Path | None = None,
        settings: "Settings | None" = None,
    ) -> None:
        self._store: dict[str, _SessionEntry] = {}
        self._lock = threading.RLock()
        self._ttl = ttl_seconds
        self._cleanup_interval = cleanup_interval
        self._cleanup_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._persist_path = persist_path
        self._settings = settings
        self._clients: dict[str, TeraBoxClient] = {}  # cache client per sid

    # ----------------------------- persistensi ------------------------------
    def _load_from_disk(self) -> None:
        """Pulihkan session dari file. Dipanggil sekali saat start."""
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return

        now = time.time()
        for sid, data in raw.items():
            created = float(data.get("created_at", 0))
            ndus = data.get("ndus", "")
            if not ndus or now - created > self._ttl:
                continue
            client = self._build_client(ndus)
            if client is None:
                continue
            try:
                client.init_tokens()
            except Exception:
                continue
            self._store[sid] = _SessionEntry(
                client=client, created_at=created, accessed_at=now
            )

    def _save_to_disk(self) -> None:
        """Tulis session ke file."""
        if not self._persist_path:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                sid: {"ndus": e.client.ndus, "created_at": e.created_at}
                for sid, e in self._store.items()
            }
            tmp = self._persist_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(self._persist_path)
            self._persist_path.chmod(0o600)
        except OSError:
            pass

    def _build_client(self, ndus: str) -> "TeraBoxClient | None":
        """Buat TeraBoxClient baru dari cookie ndus."""
        if self._settings is None:
            return None
        from .terabox import TeraBoxClient
        return TeraBoxClient(ndus, self._settings)

    # ----------------------------- API store --------------------------------
    def create(self, client: "TeraBoxClient") -> str:
        """Simpan client, return session ID."""
        sid = secrets.token_urlsafe(24)
        with self._lock:
            self._store[sid] = _SessionEntry(client=client)
            self._clients[sid] = client
            self._save_to_disk()
        return sid

    def get(self, sid: str) -> "TeraBoxClient | None":
        """Ambil client & refresh accessed_at. Return None jika expired/tidak ada."""
        with self._lock:
            entry = self._store.get(sid)
            if not entry:
                return None
            if time.time() - entry.created_at > self._ttl:
                del self._store[sid]
                self._clients.pop(sid, None)
                self._save_to_disk()
                return None
            entry.accessed_at = time.time()
            return entry.client

    def delete(self, sid: str) -> None:
        """Hapus session."""
        with self._lock:
            self._store.pop(sid, None)
            self._clients.pop(sid, None)
            self._save_to_disk()

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
                self._clients.pop(sid, None)
            if expired:
                self._save_to_disk()

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
        from ..config import SESSION_FILE, SETTINGS
        _session_store = SessionStore(
            ttl_seconds=3600 if SETTINGS.session_cookie_secure else 86400,
            cleanup_interval=3600,
            persist_path=SESSION_FILE,
            settings=SETTINGS,
        )
        _session_store._load_from_disk()
    return _session_store


def init_session_store(settings: "Settings") -> SessionStore:
    """Dipanggil sekali di create_app()."""
    global _session_store
    from ..config import SESSION_FILE

    _session_store = SessionStore(
        ttl_seconds=86400,
        cleanup_interval=3600,
        persist_path=SESSION_FILE,
        settings=settings,
    )
    _session_store._load_from_disk()
    return _session_store
