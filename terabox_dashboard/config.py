"""Konfigurasi terpusat & konstanta."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Final

# ----------------------------- host & identitas -----------------------------
DEFAULT_HOST: Final[str] = "https://dm.1024terabox.com"
TERABOX_HOST: Final[str] = os.environ.get("TERABOX_HOST", DEFAULT_HOST)

APP_ID: Final[str] = "250528"
APP_PARAMS: Final[dict[str, str]] = {
    "app_id": APP_ID,
    "web": "1",
    "channel": "dubox",
    "clienttype": "0",
}

USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
)

# ----------------------------- keystore lokal -------------------------------
STATE_DIR: Final[Path] = Path(
    os.environ.get("TERABOX_STATE_DIR", Path.home() / ".terabox_dashboard")
)
SECRET_KEY_FILE: Final[Path] = STATE_DIR / "secret_key"
SESSION_FILE: Final[Path] = STATE_DIR / "sessions.json"


def load_or_create_secret_key() -> str:
    """Baca secret key dari file, atau buat baru bila belum ada.
    Disimpan agar session Flask tidak invalid setiap restart.
    """
    env = os.environ.get("SECRET_KEY")
    if env:
        return env
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if SECRET_KEY_FILE.exists():
            val = SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
            if val:
                return val
        val = secrets.token_hex(32)
        SECRET_KEY_FILE.write_text(val, encoding="utf-8")
        SECRET_KEY_FILE.chmod(0o600)
        return val
    except OSError:
        # Filesystem tidak writable -> fallback ke key acak per-proses
        return secrets.token_hex(32)

# ----------------------------- keamanan / SSRF ------------------------------
ALLOWED_HOST_SUFFIXES: Final[tuple[str, ...]] = (
    "terabox.com",
    "1024terabox.com",
    "1024tera.com",
    "terabox.app",
    "teraboxcdn.com",
    "dubox.com",
    "baidupcs.com",
    "terabox1024.com",
)

# ----------------------------- operasi file ---------------------------------
VALID_OPERATIONS: Final[frozenset[str]] = frozenset({"rename", "move", "copy", "delete"})

# ----------------------------- cache & session ------------------------------
DLINK_CACHE_TTL_SECONDS: Final[int] = 600        # 10 menit
SESSION_TTL_SECONDS: Final[int] = 24 * 60 * 60   # 24 jam
SESSION_CLEANUP_INTERVAL: Final[int] = 60 * 60   # 1 jam

# ----------------------------- pagination -----------------------------------
DEFAULT_PAGE_SIZE: Final[int] = 1000
MAX_PAGE_SIZE: Final[int] = 2000

# ----------------------------- streaming ------------------------------------
VALID_HLS_QUALITIES: Final[tuple[str, ...]] = ("480", "720", "1080")

# ----------------------------- dataclass settings ---------------------------
@dataclass(slots=True, frozen=True)
class Settings:
    """Settings runtime yang bisa di-override via env."""
    host: str = TERABOX_HOST
    secret_key: str = load_or_create_secret_key()
    session_cookie_httponly: bool = True
    session_cookie_samesite: str = "Lax"
    session_cookie_secure: bool = os.environ.get("TERABOX_FORCE_HTTPS", "0") == "1"
    debug: bool = os.environ.get("TERABOX_DEBUG", "0") == "1"

    @property
    def base_url(self) -> str:
        return self.host.rstrip("/")


SETTINGS = Settings()
