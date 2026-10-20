"""TeraBox API client: auth, quota, list, file ops, dlink, streaming."""
from __future__ import annotations

import json
import re
import time
import urllib.parse as up
from typing import TYPE_CHECKING, Any

import requests

if TYPE_CHECKING:
    from ..config import Settings

from ..config import APP_PARAMS, USER_AGENT


class TeraBoxClient:
    """Client untuk berinteraksi dengan API web TeraBox (unofficial)."""

    def __init__(self, ndus: str, settings: "Settings") -> None:
        self._settings = settings
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Referer": settings.base_url + "/main?category=all",
            "Origin": settings.base_url,
        })
        # Set cookie di domain yang benar
        self._session.cookies.set("ndus", ndus, domain=".1024terabox.com")
        self._session.cookies.set("ndus", ndus, domain=".terabox.com")
        self._session.cookies.set("PANWEB", "1", domain=".1024terabox.com")
        self._session.cookies.set("PANWEB", "1", domain=".terabox.com")

        self._js_token: str = ""
        self._bdstoken: str = ""
        self._dlink_cache: dict[str, tuple[float, str]] = {}  # path -> (expires_at, dlink)
        self._quota_cache: tuple[float, dict] | None = None  # (expires_at, quota_dict)
        self._hls_cache: dict[str, tuple[float, str]] = {}  # "path:quality" -> (expires_at, manifest)

    # ----------------------------- token init -------------------------------
    def init_tokens(self) -> None:
        """Ambil jsToken & bdstoken dari halaman main."""
        resp = self._session.get(self._settings.base_url + "/main?category=all", timeout=25)
        html = up.unquote(resp.text)

        # jsToken
        m = re.search(r'fn\("([^"]+)"\)', html)
        self._js_token = m.group(1) if m else ""

        # bdstoken
        m = re.search(r'"bdstoken"\s*:\s*"([0-9a-f]+)"', html)
        if m:
            self._bdstoken = m.group(1)
        else:
            # Fallback ke API
            j = self._api_call("/api/gettemplatevariable", {"fields": '["bdstoken"]'})
            self._bdstoken = (j.get("result") or {}).get("bdstoken", "")

    # ----------------------------- low-level API ----------------------------
    def _api_call(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        post: bool = False,
    ) -> dict[str, Any]:
        """Panggil API TeraBox dengan parameter standar."""
        merged_params = {
            **APP_PARAMS,
            "jsToken": self._js_token,
            "bdstoken": self._bdstoken,
            **(params or {}),
        }
        url = self._settings.base_url + path
        try:
            resp = self._session.request(
                "POST" if post else "GET",
                url,
                params=merged_params,
                data=data,
                timeout=30,
            )
        except requests.RequestException as e:
            return {"errno": -1, "error": f"Network error: {e.__class__.__name__}"}

        try:
            return resp.json()
        except ValueError:
            return {"errno": -1, "error": resp.text[:200]}

    # ----------------------------- quota ------------------------------------
    def quota(self) -> dict[str, Any] | None:
        """Ambil info kuota (total, used). Cache 60 detik."""
        now = time.time()
        if self._quota_cache and self._quota_cache[0] > now:
            return self._quota_cache[1]

        j = self._api_call("/api/quota", {"checkfree": 1})
        if j.get("errno") == 0:
            result = j
            self._quota_cache = (now + 60, result)
            return result
        return None

    # ----------------------------- list files -------------------------------
    def list_files(
        self,
        dir_path: str = "/",
        order: str = "time",
        page: int = 1,
        num: int = 1000,
    ) -> dict[str, Any]:
        """List file di folder. Return raw API response."""
        params = {
            "dir": dir_path,
            "num": min(num, 2000),
            "page": page,
            "order": order,
            "desc": 1,
            "showempty": 0,
        }
        return self._api_call("/api/list", params)

    # ----------------------------- file operations --------------------------
    def file_op(self, opera: str, filelist: list[dict]) -> dict[str, Any]:
        """Operasi file: rename, move, copy, delete."""
        data = {"filelist": json.dumps(filelist)}
        params = {"method": "filemanager", "opera": opera}
        return self._api_call("/rest/2.0/xpan/file", params, data=data, post=True)

    def mkdir(self, path: str) -> dict[str, Any]:
        """Buat folder baru."""
        data = {
            "path": path,
            "isdir": "1",
            "size": "0",
            "block_list": "[]",
            "rtype": "1",
        }
        params = {"method": "create"}
        return self._api_call("/rest/2.0/xpan/file", params, data=data, post=True)

    # ----------------------------- dlink (download link) --------------------
    def get_dlink(self, path: str) -> str | None:
        """Ambil direct download link (cache 10 menit)."""
        now = time.time()
        cached = self._dlink_cache.get(path)
        if cached and cached[0] > now:
            return cached[1]

        j = self._api_call("/api/filemetas", {
            "dlink": 1,
            "target": json.dumps([path]),
        })
        try:
            dlink = j["info"][0]["dlink"]
        except Exception:
            return None

        self._dlink_cache[path] = (now + 600, dlink)
        return dlink

    # ----------------------------- HLS streaming ----------------------------
    def get_hls_manifest(self, path: str, quality: str) -> str | None:
        """Ambil manifest HLS (M3U8) untuk kualitas tertentu (cache 2 menit)."""
        if quality not in ("480", "720", "1080"):
            return None

        cache_key = f"{path}:{quality}"
        now = time.time()
        cached = self._hls_cache.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

        params = {
            **{"app_id": "250528", "web": "1", "channel": "dubox", "clienttype": "0"},
            "path": path,
            "type": f"M3U8_AUTO_{quality}",
            "vip": 1,
            "jsToken": self._js_token,
        }
        resp = self._session.get(
            self._settings.base_url + "/api/streaming",
            params=params,
            timeout=30,
        )
        if not resp.text.startswith("#EXTM3U"):
            return None

        self._hls_cache[cache_key] = (now + 120, resp.text)
        return resp.text

    # ----------------------------- properties -------------------------------
    @property
    def js_token(self) -> str:
        return self._js_token

    @property
    def bdstoken(self) -> str:
        return self._bdstoken
