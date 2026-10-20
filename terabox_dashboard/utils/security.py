"""Utilitas keamanan: parsing cookie, SSRF guard, normalisasi path."""
from __future__ import annotations

import ipaddress
import re
import urllib.parse as up
from typing import Final

from ..config import ALLOWED_HOST_SUFFIXES

# ----------------------------- cookie parsing -------------------------------
_NDUS_PATTERN: Final[re.Pattern[str]] = re.compile(r"ndus=([^;\s]+)")
_MIN_NDUS_LEN: Final[int] = 10


def parse_ndus(raw: str) -> str | None:
    """Ekstrak nilai ndus dari string cookie mentah atau 'ndus=...'.
    Return None jika tidak valid.
    """
    if not raw:
        return None
    m = _NDUS_PATTERN.search(raw)
    val = m.group(1) if m else raw.strip()
    return val if len(val) >= _MIN_NDUS_LEN else None


# ----------------------------- SSRF guard -----------------------------------
_PRIVATE_IP_NETWORKS: Final[tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]] = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)


def _is_private_ip(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(ip in net for net in _PRIVATE_IP_NETWORKS)


def allowed_url(url: str) -> bool:
    """Validasi URL aman untuk proxy (hindari SSRF).
    - Hanya scheme http/https
    - Hostname harus suffix whitelist
    - Bukan IP private / loopback
    """
    try:
        p = up.urlparse(url)
    except Exception:
        return False

    if p.scheme not in ("http", "https"):
        return False

    host = (p.hostname or "").lower()
    if not host:
        return False

    if _is_private_ip(host):
        return False

    return any(host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_HOST_SUFFIXES)


# ----------------------------- path normalization ---------------------------
def normalize_path(base: str, path: str) -> str:
    """Gabungkan base + path, lalu normalisasi.
    Mencegah traversal di luar base.
    """
    base = base.rstrip("/")
    path = path.lstrip("/")
    joined = up.urljoin(base + "/", path)
    # Pastikan tetap di bawah base
    if not joined.startswith(base):
        return base
    return joined


def validate_operation(op: str) -> bool:
    """Cek operasi file apakah di whitelist."""
    from ..config import VALID_OPERATIONS
    return op in VALID_OPERATIONS
