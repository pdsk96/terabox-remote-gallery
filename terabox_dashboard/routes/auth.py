"""Authentication routes: login, logout, me."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from ..config import SETTINGS
from ..services import get_session_store, TeraBoxClient
from ..utils import parse_ndus

auth_bp = Blueprint("auth", __name__, url_prefix="/api")


@auth_bp.post("/login")
def login():
    """Login dengan cookie ndus.
    Body JSON: { ndus: "nilai ndus atau ndus=..." }
    """
    raw = (request.get_json(silent=True) or {}).get("ndus", "").strip()
    ndus = parse_ndus(raw)
    if not ndus:
        return jsonify(ok=False, error="Cookie ndus tidak valid (min 10 karakter)")

    client = TeraBoxClient(ndus, SETTINGS)

    # Step 1: ambil jsToken & bdstoken
    try:
        client.init_tokens()
    except Exception as e:
        return jsonify(
            ok=False,
            error=f"Gagal ambil token: {e.__class__.__name__}",
            step="init_tokens",
        )

    # Step 2: cek quota (validasi cookie aktif)
    quota_info = client.quota()
    if not quota_info:
        # Coba ambil error detail dari quota
        j = client._api_call("/api/quota", {"checkfree": 1})
        errno = j.get("errno")
        errmsg = j.get("error", "tidak diketahui")
        return jsonify(
            ok=False,
            error=f"Login gagal: cookie ndus kedaluwarsa/salah atau akun tidak aktif",
            step="quota",
            errno=errno,
            detail=str(errmsg)[:200],
        )

    store = get_session_store()
    sid = store.create(client)
    session["sid"] = sid
    session.permanent = True

    warn = None if client.bdstoken else "bdstoken tidak ditemukan; operasi tulis mungkin gagal"
    return jsonify(
        ok=True,
        quota=_quota_info(quota_info),
        warn=warn,
        step="ok",
    )


@auth_bp.post("/logout")
def logout():
    """Logout & hapus session."""
    sid = session.pop("sid", None)
    if sid:
        get_session_store().delete(sid)
    return jsonify(ok=True)


@auth_bp.get("/me")
def me():
    """Cek status login & quota."""
    sid = session.get("sid")
    if not sid:
        return jsonify(ok=False, quota=None)

    client = get_session_store().get(sid)
    if not client:
        session.pop("sid", None)
        return jsonify(ok=False, quota=None)

    quota_info = client.quota()
    return jsonify(ok=bool(quota_info), quota=_quota_info(quota_info) if quota_info else None)


def _quota_info(q: dict) -> dict[str, int]:
    return {"total": q.get("total", 0), "used": q.get("used", 0)}
