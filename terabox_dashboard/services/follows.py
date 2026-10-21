"""Daftar channel yang diikuti, disimpan lokal.

TeraBox tidak menyediakan endpoint subscribe/follow channel, jadi channel
yang "diikuti" dicatat di sisi server sebagai daftar nama uploader
(diambil dari `share_user.name` pada feed resource).

Disimpan di ~/.terabox_dashboard/follows.json
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final

from ..config import STATE_DIR

FOLLOWS_FILE: Final[Path] = STATE_DIR / "follows.json"


@dataclass(slots=True)
class FollowedChannel:
    """Channel (uploader) yang diikuti user."""

    name: str
    added_at: float = field(default_factory=time.time)
    # share link terakhir yang terlihat dari channel ini (bisa dipakai untuk resolve)
    last_link: str = ""
    last_share_id: int = 0
    last_uk: int = 0
    item_count: int = 0


class FollowStore:
    """Simpan daftar channel yang diikuti (thread-safe, persist ke disk)."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or FOLLOWS_FILE
        self._lock = threading.RLock()
        self._items: dict[str, FollowedChannel] = {}
        self._load()

    # ----------------------------- persistensi -------------------------------
    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for name, data in raw.items():
            try:
                self._items[name] = FollowedChannel(
                    name=data.get("name", name),
                    added_at=float(data.get("added_at", 0)),
                    last_link=data.get("last_link", ""),
                    last_share_id=int(data.get("last_share_id", 0)),
                    last_uk=int(data.get("last_uk", 0)),
                    item_count=int(data.get("item_count", 0)),
                )
            except (TypeError, ValueError):
                continue

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {n: asdict(c) for n, c in self._items.items()}
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self._path)
        except OSError:
            pass

    # ----------------------------- API ----------------------------------------
    def names(self) -> list[str]:
        """Nama channel yang diikuti."""
        with self._lock:
            return list(self._items.keys())

    def all(self) -> list[FollowedChannel]:
        with self._lock:
            return sorted(self._items.values(), key=lambda c: c.added_at, reverse=True)

    def is_followed(self, name: str) -> bool:
        with self._lock:
            return name in self._items

    def follow(self, name: str, link: str = "", share_id: int = 0, uk: int = 0) -> FollowedChannel:
        """Ikuti channel (idempoten)."""
        name = (name or "").strip()
        with self._lock:
            existing = self._items.get(name)
            if existing:
                if link:
                    existing.last_link = link
                if share_id:
                    existing.last_share_id = share_id
                if uk:
                    existing.last_uk = uk
            else:
                existing = FollowedChannel(
                    name=name, last_link=link, last_share_id=share_id, last_uk=uk
                )
                self._items[name] = existing
            self._save()
            return existing

    def unfollow(self, name: str) -> bool:
        with self._lock:
            existed = self._items.pop(name, None) is not None
            if existed:
                self._save()
            return existed

    def touch(self, name: str, link: str = "", share_id: int = 0, uk: int = 0) -> None:
        """Perbarui metadata channel tanpa mengubah status follow."""
        with self._lock:
            c = self._items.get(name)
            if not c:
                return
            if link:
                c.last_link = link
            if share_id:
                c.last_share_id = share_id
            if uk:
                c.last_uk = uk
            c.item_count += 1
            self._save()


_store: FollowStore | None = None


def get_follow_store() -> FollowStore:
    global _store
    if _store is None:
        _store = FollowStore()
    return _store
