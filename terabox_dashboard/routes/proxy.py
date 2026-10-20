"""Proxy routes untuk media streaming & download."""
from __future__ import annotations

from flask import Blueprint, Response, abort, request, session, stream_with_context

from ..config import SETTINGS, VALID_HLS_QUALITIES
from ..services import get_session_store
from ..utils import allowed_url, rewrite_m3u8

proxy_bp = Blueprint("proxy", __name__, url_prefix="/proxy")


def _require_client():
    sid = session.get("sid")
    if not sid:
        abort(401)
    client = get_session_store().get(sid)
    if not client:
        abort(401)
    return client


def _relay(client, url: str):
    """Stream response dari URL ke client dengan support Range & CORS."""
    headers = {}
    if request.headers.get("Range"):
        headers["Range"] = request.headers["Range"]

    resp = client._session.get(url, headers=headers, stream=True, timeout=30)

    if not allowed_url(resp.url):
        resp.close()
        abort(403)

    content_type = resp.headers.get("Content-Type", "").lower()

    # HLS manifest rewrite
    if ".m3u8" in url.split("?")[0] or "mpegurl" in content_type:
        return Response(
            rewrite_m3u8(resp.text, resp.url),
            content_type="application/vnd.apple.mpegurl",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Range",
                "Access-Control-Expose-Headers": "Content-Range, Content-Length",
                "Cache-Control": "public, max-age=120",
            },
        )

    # Pass-through headers
    keep = ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges", "Cache-Control")
    hdrs = {k: resp.headers[k] for k in keep if k in resp.headers}
    hdrs["Access-Control-Allow-Origin"] = "*"
    hdrs["Access-Control-Allow-Headers"] = "Range"
    hdrs["Access-Control-Expose-Headers"] = "Content-Range, Content-Length"

    return Response(
        stream_with_context(resp.iter_content(65536)),
        status=resp.status_code,
        headers=hdrs,
    )


@proxy_bp.get("/u")
def proxy_u():
    """Proxy generic URL (thumbnail, segment, dll)."""
    client = _require_client()
    url = request.args.get("u", "")
    if not allowed_url(url):
        abort(403)
    return _relay(client, url)


@proxy_bp.get("/file")
def proxy_file():
    """Proxy direct download link file."""
    client = _require_client()
    path = request.args.get("path", "")
    if not path:
        abort(400)

    dlink = client.get_dlink(path)
    if not dlink or not allowed_url(dlink):
        abort(404)
    return _relay(client, dlink)


@proxy_bp.get("/hls")
def proxy_hls():
    """Proxy HLS manifest dengan rewrite segment ke /proxy/u."""
    client = _require_client()
    path = request.args.get("path", "")
    quality = request.args.get("q", "480")

    if quality not in VALID_HLS_QUALITIES:
        abort(400)

    manifest = client.get_hls_manifest(path, quality)
    if not manifest:
        abort(502)

    return Response(
        rewrite_m3u8(manifest, SETTINGS.base_url),
        content_type="application/vnd.apple.mpegurl",
    )
