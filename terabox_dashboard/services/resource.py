"""Service untuk feed Channel/resource TeraBox.

Endpoint yang dipakai (semua terverifikasi live, errno 0):
  GET  /api/resource/hotrecommend     -> feed utama (type=2 single video, 3 movie/series)
  GET  /api/resource/list              -> feed dengan filter kategori
  GET  /api/resource/recommend         -> pencarian saran
  GET  /api/resource/searchaggregation  -> pencarian agregat
  GET  /api/resource/searchhistory     -> riwayat pencarian
  GET  /resource/getResCycleTags       -> daftar kategori (per country)
  GET  /api/resconsume/gettags         -> daftar channel (Movies, TV Show, ...)
  GET  /api/shorturlinfo               -> resolve share link -> fs_id/path
  POST /share/transfer                 -> simpan file share ke drive sendiri
  GET  /share/querysurltransfer        -> cek status transfer
  GET  /share/teratransfer/sharelist   -> daftar share link milik sendiri
  GET  /api/favor/list                 -> item yang di-like
  POST /api/favor/mark                 -> like / unlike
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from .terabox import TeraBoxClient

# clienttype 8 wajib untuk endpoint /api/resource/* (bukan 0 seperti endpoint lain)
RESOURCE_CLIENTTYPE = 8

# tipe konten pada /api/resource/hotrecommend
KIND_ALL = "99"
KIND_VIDEO = "2"       # file video tunggal
KIND_SERIES = "3"      # folder film / series

_SHORTURL_RE = re.compile(r"https?://[^/\s]+/s/([A-Za-z0-9_-]+)")


def extract_shorturl(url: str) -> str:
    """Ambil kode shorturl dari share link TeraBox.

    Contoh: https://1024terabox.com/s/1aBcDeF -> 1aBcDeF
    Menerima juga input mentah '1aBcDeF'.
    """
    url = (url or "").strip()
    m = _SHORTURL_RE.search(url)
    if m:
        return m.group(1)
    if "/" in url:
        return url.rsplit("/", 1)[-1]
    return url


class ResourceService:
    """Wrapper atas endpoint feed channel & share TeraBox."""

    def __init__(self, client: TeraBoxClient) -> None:
        self._c = client
        self._cache: dict[str, tuple[float, Any]] = {}

    # ----------------------------- cache helper -----------------------------
    def _cached(self, key: str, ttl: int, factory):
        now = time.time()
        hit = self._cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
        val = factory()
        self._cache[key] = (now + ttl, val)
        return val

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = {"clienttype": RESOURCE_CLIENTTYPE, **(params or {})}
        return self._c._api_call(path, merged)

    # ----------------------------- feed -------------------------------------
    def hot_recommend(
        self, kind: str = KIND_ALL, page: int = 1, count: int = 20
    ) -> list[dict[str, Any]]:
        """Feed utama resource. kind: '99' semua, '2' video, '3' series."""
        j = self._get("/api/resource/hotrecommend", {
            "count": str(count), "page": page, "type": str(kind),
        })
        if j.get("errno") != 0:
            return []
        return (j.get("data") or {}).get("movie") or []

    def list_resources(
        self,
        resource_kind: str = KIND_ALL,
        category: str = "",
        page: int = 1,
        count: int = 20,
        country: str = "",
    ) -> list[dict[str, Any]]:
        """Feed dengan filter kategori (resource_category)."""
        params: dict[str, Any] = {
            "type": "2",
            "count": str(count),
            "need_area": 0,
            "use_weight": 1,
            "page": page,
            "resource_category": category or "",
            "resource_kind": str(resource_kind),
        }
        if country:
            params["country"] = country
        j = self._get("/api/resource/list", params)
        if j.get("errno") != 0:
            return []
        return (j.get("data") or {}).get("detail") or []

    def aggregate_feed(
        self, kind: str = KIND_ALL, pages: int = 3, count: int = 20
    ) -> list[dict[str, Any]]:
        """Kumpulkan beberapa halaman feed lalu dedup berdasarkan fs_id."""
        seen: set[int] = set()
        out: list[dict[str, Any]] = []
        for p in range(1, max(1, pages) + 1):
            for item in self.hot_recommend(kind=kind, page=p, count=count):
                fs_id = ((item.get("share_info") or {}).get("fs_id"))
                key = fs_id if isinstance(fs_id, int) else len(out)
                if key in seen:
                    continue
                seen.add(key)
                out.append(item)
        return out

    # ----------------------------- kategori & channel ------------------------
    def categories(self, country: str = "") -> tuple[list[str], str]:
        """Daftar kategori (Movie, TV show, Animation, ...) dan negara yang dipakai.

        Tidak semua country punya konten resource. Kalau negara yang diminta
        kosong, coba negara lain sampai ketemu. Return (kategori, country_terpakai).
        """
        def fetch() -> tuple[list[str], str]:
            order = [country] if country else []
            order += [c for c in ("ID", "PH", "TH", "VN", "MY", "IN", "BR", "MX", "EG", "KR", "RU")
                      if c not in order]
            for ctry in order:
                j = self._get("/resource/getResCycleTags", {
                    "country": ctry, "tag_type": "type",
                })
                if j.get("errno") != 0:
                    continue
                tags = (j.get("data") or {}).get("tags") or []
                vals: list[str] = []
                for t in tags:
                    raw = t.get("tag_value") or ""
                    for v in raw.split(","):
                        v = v.strip()
                        if v and v != "All types" and v not in vals:
                            vals.append(v)
                if vals:
                    return vals, ctry
            return [], country or "ID"

        return self._cached(f"cats:{country}", 900, fetch)

    def channels(self) -> list[dict[str, Any]]:
        """Daftar channel bawaan TeraBox (Movies, TV Show, Animation, ...)."""
        def fetch() -> list[dict[str, Any]]:
            j = self._c._api_call("/api/resconsume/gettags", {})
            if j.get("errno") != 0:
                return []
            chans = (j.get("data") or {}).get("channels") or []
            return [
                {"id": ch.get("channel_id"), "name": ch.get("name"), "weight": ch.get("weight")}
                for ch in chans
            ]

        return self._cached("channels", 900, fetch)

    # ----------------------------- pencarian ----------------------------------
    def search(self, content: str, count: int = 30) -> list[dict[str, Any]]:
        """Pencarian resource (recommend = hasil langsung)."""
        if not content.strip():
            return []
        j = self._get("/api/resource/recommend", {
            "content": content, "count": str(count),
        })
        if j.get("errno") != 0:
            return []
        data = j.get("data") or {}
        items = data.get("detail") or data.get("movie") or []
        if isinstance(items, dict):
            items = items.get("resource_search_result") or []
        return items

    def search_aggregate(self, content: str) -> list[dict[str, Any]]:
        """Pencarian agregat (mirip suggestion di kotak search)."""
        if not content.strip():
            return []
        j = self._get("/api/resource/searchaggregation", {
            "content": content, "input": "writing", "type": 99,
        })
        if j.get("errno") != 0:
            return []
        detail = (j.get("data") or {}).get("detail") or {}
        return detail.get("resource_search_result") or []

    def search_history(self, count: int = 10) -> list[str]:
        j = self._get("/api/resource/searchhistory", {"page": 1, "count": str(count)})
        if j.get("errno") != 0:
            return []
        return [it.get("content", "") for it in (j.get("data") or {}).get("list") or []]

    def clear_search_history(self) -> bool:
        j = self._get("/api/resource/searchhistoryclean", {})
        return j.get("errno") == 0

    # ----------------------------- share link --------------------------------
    def resolve_share(self, shorturl: str) -> dict[str, Any]:
        """Resolve share link jadi daftar file (fs_id, path, isdir)."""
        code = extract_shorturl(shorturl)
        if not code:
            return {"ok": False, "error": "Short URL tidak valid"}
        j = self._c._api_call("/api/shorturlinfo", {"shorturl": code, "root": 1})
        if j.get("errno") != 0:
            return {"ok": False, "error": f"errno {j.get('errno')}", "errno": j.get("errno")}
        return {
            "ok": True,
            "shorturl": code,
            "shareid": j.get("shareid"),
            "uk": j.get("uk"),
            "uk_str": j.get("uk_str"),
            "share_username": j.get("share_username"),
            "channel": j.get("channel"),
            "description": j.get("description"),
            "expiredtype": j.get("expiredtype"),
            "fcount": j.get("fcount"),
            "list": j.get("list") or [],
        }

    def transfer_status(self, share_id: int, from_uk: int) -> dict[str, Any]:
        """Cek apakah share bisa di-transfer (has_transferred)."""
        j = self._c._api_call("/share/querysurltransfer", {
            "sid": share_id, "suk": from_uk,
        })
        if j.get("errno") != 0:
            return {"ok": False, "error": f"errno {j.get('errno')}"}
        return {"ok": True, "has_transferred": (j.get("data") or {}).get("has_transferred")}

    def transfer(
        self,
        share_id: int,
        from_uk: int,
        fs_ids: list[int],
        dest_path: str,
        ondup: str = "newcopy",
    ) -> dict[str, Any]:
        """Simpan file dari share orang lain ke drive sendiri (server-to-server).

        TeraBox mengembalikan errno 17 dengan info[] berisi error per-item.
        Parsing info[] untuk pesan error yang bermakna (mis. errno 120 = share
        kadaluarsa, errno 4 = konflik path).
        """
        if not fs_ids:
            return {"ok": False, "error": "Tidak ada file yang dipilih"}
        dest = dest_path if dest_path.startswith("/") else "/" + dest_path
        params = {
            "shareid": share_id,
            "from": from_uk,
            "ondup": ondup,
            "async": 1,
        }
        data = {"fsidlist": json.dumps(fs_ids), "path": dest}
        j = self._c._api_call("/share/transfer", params, data=data, post=True)
        if j.get("errno") == 0:
            return {"ok": True, "errno": 0}
        # Parsing info[] untuk detail error per-item
        infos = j.get("info") or []
        if isinstance(infos, list):
            msgs = []
            for info in infos:
                if isinstance(info, dict):
                    e = info.get("errno")
                    p = info.get("path")
                    if e == 120:
                        msgs.append(f"Share kadaluarsa/tidak tersedia ({p or ''})")
                    elif e == 4:
                        msgs.append(f"Konflik path/izin ({p or ''})")
                    else:
                        msgs.append(f"errno {e} ({p or ''})")
            detail = "; ".join(msgs) if msgs else f"errno {j.get('errno')}"
        else:
            detail = j.get("errmsg") or f"errno {j.get('errno')}"
        return {"ok": False, "errno": j.get("errno"), "errmsg": detail}

    def my_shares(self, page: int = 1, num: int = 50) -> list[dict[str, Any]]:
        """Daftar share link milik sendiri."""
        j = self._c._api_call("/share/teratransfer/sharelist", {"page": page, "num": num})
        if j.get("errno") != 0:
            return []
        return (j.get("data") or {}).get("share_list") or []

    # ----------------------------- like --------------------------------------
    def favor_list(self, page: int = 1, num: int = 50) -> list[dict[str, Any]]:
        j = self._c._api_call("/api/favor/list", {"page": page, "num": num})
        if j.get("errno") != 0:
            return []
        return j.get("list") or []

    def favor_mark(self, fs_id: int, flag: int) -> bool:
        """Like (flag=1) / unlike (flag=0)."""
        j = self._c._api_call("/api/favor/mark", {}, data={"flag": flag, "fs_id": fs_id},
                              post=True)
        return j.get("errno") == 0


def normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Ringkas item resource menjadi struktur seragam untuk frontend."""
    si = item.get("share_info") or {}
    ri = item.get("resource_info") or {}
    su = item.get("share_user") or {}
    cover = si.get("cover") or {}
    thumbs = si.get("thumbs") or {}
    thumb = ""
    for src in (cover, thumbs):
        if isinstance(src, dict):
            for k in ("url3", "url2", "url1", "icon"):
                if src.get(k):
                    thumb = src[k]
                    break
        if thumb:
            break
    return {
        "fs_id": si.get("fs_id"),
        "share_id": si.get("share_id"),
        "uk": si.get("uk"),
        "name": si.get("server_filename", ""),
        "path": si.get("path", ""),
        "link": si.get("link", ""),
        "size": si.get("size", 0),
        "duration": si.get("duration", 0),
        "ctime": si.get("server_ctime", 0),
        "thumb": thumb,
        "channel": su.get("name", ""),
        "channel_avatar": su.get("head_url", ""),
        "kind": ri.get("type"),
        "is_dir": bool(si.get("is_dir", ri.get("is_dir"))),
        "year": ri.get("product_year", ""),
        "liked": ri.get("liked", 0),
        "liked_count": ri.get("liked_count", 0),
        "tv_cnt": ri.get("tv_cnt", 0),
    }
