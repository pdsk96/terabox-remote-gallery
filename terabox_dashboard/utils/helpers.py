"""Helper functions: formatting, normalization, m3u8 rewrite."""
from __future__ import annotations

import re
import urllib.parse as up
from typing import TypedDict


class FileInfo(TypedDict):
    id: int | None
    path: str
    name: str
    dir: bool
    size: int
    mtime: int
    cat: int
    thumb: str


def norm_file(raw: dict) -> FileInfo:
    """Normalisasi item file dari API TeraBox ke struktur konsisten."""
    th = raw.get("thumbs") or {}
    return FileInfo(
        id=raw.get("fs_id"),
        path=raw["path"],
        name=raw.get("server_filename", ""),
        dir=bool(raw.get("isdir")),
        size=raw.get("size", 0),
        mtime=raw.get("server_mtime", 0),
        cat=raw.get("category", 6),
        thumb=th.get("url3") or th.get("url2") or th.get("url1") or "",
    )


def fmt_size(num: int) -> str:
    """Format bytes jadi string human-readable."""
    if not num:
        return ""
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    n = float(num)
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    return f"{n:.1f} {units[i]}" if i else f"{int(n)} {units[i]}"


def join_path(base: str, name: str) -> str:
    """Gabungkan path folder + nama file/folder."""
    base = base.rstrip("/")
    return f"{base}/{name}" if base else f"/{name}"


def category_label(cat: int) -> str:
    """Label kategori untuk UI."""
    return {1: "video", 2: "audio", 3: "image"}.get(cat, "")


def rewrite_m3u8(content: str, base_url: str) -> str:
    """Rewrite URL di m3u8 agar melewati proxy /proxy/u."""
    def replacer(match: re.Match[str]) -> str:
        uri = match.group(1)
        absolute = up.urljoin(base_url, uri)
        return f'URI="/proxy/u?u={up.quote(absolute, safe="")}"'

    out_lines: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            # Rewrite URI="..." di tag EXT-X-KEY, EXT-X-MAP, dll
            line = re.sub(r'URI="([^"]+)"', replacer, line)
        elif stripped:
            # Baris segment URI relatif/absolut
            absolute = up.urljoin(base_url, stripped)
            line = f"/proxy/u?u={up.quote(absolute, safe='')}"
        out_lines.append(line)
    return "\n".join(out_lines)
