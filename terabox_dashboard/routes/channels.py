"""Routes untuk tab Channel: feed, kategori, pencarian, follow, share, transfer."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from ..services.follows import get_follow_store
from ..services.resource import (
    KIND_ALL,
    KIND_SERIES,
    KIND_VIDEO,
    ResourceService,
    normalize_item,
)

channel_bp = Blueprint("channel", __name__, url_prefix="/api/channel")


def _require_client():
    sid = session.get("sid")
    if not sid:
        return None, jsonify(ok=False, error="Unauthorized"), 401
    from ..services import get_session_store
    client = get_session_store().get(sid)
    if not client:
        session.pop("sid", None)
        return None, jsonify(ok=False, error="Session expired"), 401
    return client, None, None


def _service():
    client, err, code = _require_client()
    if err:
        return None, err, code
    return ResourceService(client), None, None


def _int_arg(name: str, default: int, lo: int, hi: int) -> int:
    try:
        val = int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, val))


# ----------------------------- feed ------------------------------------------
@channel_bp.get("/feed")
def feed():
    """Feed resource. Query: kind (99/2/3), category, page, count, channel."""
    svc, err, code = _service()
    if err:
        return err, code

    kind = request.args.get("kind", KIND_ALL)
    if kind not in (KIND_ALL, KIND_VIDEO, KIND_SERIES):
        kind = KIND_ALL
    category = request.args.get("category", "").strip()
    page = _int_arg("page", 1, 1, 500)
    count = _int_arg("count", 20, 1, 50)
    channel_filter = request.args.get("channel", "").strip()
    scope = request.args.get("scope", "all")  # all | followed

    if scope == "followed":
        followed = set(get_follow_store().names())
        if not followed:
            return jsonify(ok=True, items=[], total=0, scope=scope)
        # Gunakan feed halaman yang sama dengan tab Feed agar konten konsisten.
        # Jangan agregasi halaman tambahan — supaya "Diikuti" = subset dari "Feed".
        raw = svc.hot_recommend(kind=kind, page=page, count=count)
        items = [i for i in raw if (i.get("share_user") or {}).get("name") in followed]
        # Filter by channel name (passed via `category` di frontend tab Diikuti)
        if category:
            items = [i for i in items
                     if (i.get("share_user") or {}).get("name") == category]
        return jsonify(ok=True, items=[normalize_item(i) for i in items],
                       total=len(items), scope=scope)

    if category:
        _, used_country = svc.categories(country="")
        raw = svc.list_resources(resource_kind=kind, category=category,
                                 page=page, count=count, country=used_country)
    else:
        raw = svc.hot_recommend(kind=kind, page=page, count=count)

    if channel_filter:
        raw = [i for i in raw
               if (i.get("share_user") or {}).get("name") == channel_filter]

    # Catat channel yang terlihat supaya bisa di-"follow" dari UI
    store = get_follow_store()
    for item in raw:
        su = item.get("share_user") or {}
        si = item.get("share_info") or {}
        if su.get("name") and store.is_followed(su["name"]):
            store.touch(su["name"], si.get("link", ""),
                        si.get("share_id", 0), si.get("uk", 0))

    return jsonify(ok=True, items=[normalize_item(i) for i in raw],
                   total=len(raw), scope=scope)


@channel_bp.get("/categories")
def categories():
    """Daftar kategori + channel bawaan + negara tersedia."""
    svc, err, code = _service()
    if err:
        return err, code
    country = request.args.get("country", "")
    cats, used = svc.categories(country=country)
    return jsonify(ok=True, country=used, categories=cats, channels=svc.channels())


@channel_bp.get("/countries")
def countries():
    """Negara yang punya konten feed."""
    svc, err, code = _service()
    if err:
        return err, code
    j = svc._c._api_call("/api/resconsume/getcountrys", {})
    return jsonify(ok=True, countries=(j.get("data") or {}).get("countrys") or [])


# ----------------------------- pencarian -------------------------------------
@channel_bp.get("/search")
def search():
    """Cari resource. Query: q, page, count."""
    svc, err, code = _service()
    if err:
        return err, code
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify(ok=True, items=[], total=0, q=q)
    count = _int_arg("count", 30, 1, 50)
    raw = svc.search(q, count=count)
    return jsonify(ok=True, items=[normalize_item(i) for i in raw],
                   total=len(raw), q=q)


@channel_bp.get("/search/suggest")
def search_suggest():
    """Saran pencarian (agregat)."""
    svc, err, code = _service()
    if err:
        return err, code
    q = request.args.get("q", "").strip()
    raw = svc.search_aggregate(q)
    return jsonify(ok=True, items=[normalize_item(i) for i in raw], q=q)


@channel_bp.get("/search/history")
def search_history():
    svc, err, code = _service()
    if err:
        return err, code
    return jsonify(ok=True, items=svc.search_history())


@channel_bp.post("/search/history/clear")
def clear_history():
    svc, err, code = _service()
    if err:
        return err, code
    return jsonify(ok=svc.clear_search_history())


# ----------------------------- follow ---------------------------------------
@channel_bp.get("/follows")
def list_follows():
    """Channel yang diikuti."""
    store = get_follow_store()
    return jsonify(ok=True, items=[
        {"name": c.name, "added_at": c.added_at, "last_link": c.last_link,
         "item_count": c.item_count}
        for c in store.all()
    ])


@channel_bp.post("/follow")
def follow():
    """Ikuti channel. Body: { name, link, share_id, uk }"""
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify(ok=False, error="Nama channel wajib diisi"), 400
    c = get_follow_store().follow(
        name,
        link=body.get("link", ""),
        share_id=int(body.get("share_id") or 0),
        uk=int(body.get("uk") or 0),
    )
    return jsonify(ok=True, name=c.name, item_count=c.item_count)


@channel_bp.post("/unfollow")
def unfollow():
    """Berhenti mengikuti channel. Body: { name }"""
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify(ok=False, error="Nama channel wajib diisi"), 400
    ok = get_follow_store().unfollow(name)
    return jsonify(ok=ok, name=name)


# ----------------------------- share ----------------------------------------
@channel_bp.get("/share/resolve")
def resolve_share():
    """Resolve share link -> daftar file. Query: url."""
    svc, err, code = _service()
    if err:
        return err, code
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify(ok=False, error="URL share wajib diisi"), 400
    res = svc.resolve_share(url)
    if not res.get("ok"):
        return jsonify(ok=False, error=res.get("error", "Gagal resolve share link")), 400
    res["items"] = [
        {
            "fs_id": it.get("fs_id"),
            "name": it.get("server_filename", ""),
            "path": it.get("path", ""),
            "is_dir": bool(it.get("isdir")),
            "size": it.get("size", 0),
            "category": it.get("category", 6),
            "server_mtime": it.get("server_mtime", 0),
        }
        for it in res.get("list") or []
    ]
    res["share_id"] = res.get("shareid")
    res.pop("list", None)
    res.pop("shareid", None)
    res.pop("ok", None)
    return jsonify(ok=True, **res)


@channel_bp.get("/share/mine")
def my_shares():
    """Daftar share link milik sendiri."""
    svc, err, code = _service()
    if err:
        return err, code
    page = _int_arg("page", 1, 1, 100)
    num = _int_arg("num", 50, 1, 100)
    shares = svc.my_shares(page=page, num=num)
    return jsonify(ok=True, items=[{
        "share_id": s.get("share_id"),
        "name": s.get("name", ""),
        "surl": s.get("surl", ""),
        "file_cnt": s.get("file_cnt", 0),
        "size": s.get("size", 0),
        "ctime": s.get("ctime", 0),
        "expired_day": s.get("expired_day", 0),
        "status": s.get("status", 0),
    } for s in shares])


@channel_bp.post("/share/save")
def save_share():
    """Simpan file dari share orang lain ke drive sendiri.
    Body: { share_id, uk, fs_ids: [...], path, ondup }
    """
    svc, err, code = _service()
    if err:
        return err, code
    body = request.get_json(silent=True) or {}
    share_id = body.get("share_id")
    uk = body.get("uk")
    fs_ids = body.get("fs_ids") or []
    dest = (body.get("path") or "/").strip()
    ondup = body.get("ondup") or "newcopy"

    if not share_id or not uk:
        return jsonify(ok=False, error="share_id dan uk wajib diisi"), 400
    try:
        fs_ids = [int(x) for x in fs_ids]
    except (TypeError, ValueError):
        return jsonify(ok=False, error="fs_ids harus berupa angka"), 400

    res = svc.transfer(int(share_id), int(uk), fs_ids, dest, ondup=ondup)
    if not res.get("ok"):
        return jsonify(ok=False, error=res.get("errmsg") or f"errno {res.get('errno')}"), 400
    return jsonify(ok=True, saved=len(fs_ids), path=dest)


@channel_bp.get("/share/status")
def share_status():
    """Cek status transfer sebuah share. Query: sid, suk"""
    svc, err, code = _service()
    if err:
        return err, code
    try:
        sid = int(request.args.get("sid", 0))
        suk = int(request.args.get("suk", 0))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="sid/suk harus angka"), 400
    res = svc.transfer_status(sid, suk)
    if not res.get("ok"):
        return jsonify(ok=False, error=res.get("error")), 400
    return jsonify(ok=True, has_transferred=res.get("has_transferred"))


# ----------------------------- like -----------------------------------------
@channel_bp.post("/like")
def like():
    """Like/unlike resource. Body: { fs_id, flag }"""
    svc, err, code = _service()
    if err:
        return err, code
    body = request.get_json(silent=True) or {}
    try:
        fs_id = int(body.get("fs_id", 0))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="fs_id harus angka"), 400
    if not fs_id:
        return jsonify(ok=False, error="fs_id wajib diisi"), 400
    flag = 1 if body.get("flag") in (1, True, "1", "true") else 0
    ok = svc.favor_mark(fs_id, flag)
    return jsonify(ok=ok, fs_id=fs_id, flag=flag)


@channel_bp.get("/likes")
def likes():
    """Item yang sudah di-like."""
    svc, err, code = _service()
    if err:
        return err, code
    items = svc.favor_list()
    return jsonify(ok=True, items=[
        {"fs_id": it.get("fs_id"), "name": it.get("server_filename", ""),
         "path": it.get("path", ""), "size": it.get("size", 0),
         "is_dir": bool(it.get("isdir"))}
        for it in items
    ])
