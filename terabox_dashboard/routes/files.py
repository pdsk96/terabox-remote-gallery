"""File operation routes: list, op, mkdir."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from ..config import VALID_OPERATIONS
from ..services import get_session_store
from ..utils import validate_operation, norm_file

files_bp = Blueprint("files", __name__, url_prefix="/api")


def _require_client():
    sid = session.get("sid")
    if not sid:
        return None, jsonify(ok=False, error="Unauthorized"), 401
    client = get_session_store().get(sid)
    if not client:
        session.pop("sid", None)
        return None, jsonify(ok=False, error="Session expired"), 401
    return client, None, None


@files_bp.get("/list")
def list_files():
    """List file di folder dengan pagination & sorting."""
    client, err_resp, err_code = _require_client()
    if err_resp:
        return err_resp, err_code

    dir_path = request.args.get("dir", "/")
    order = request.args.get("order", "time")
    page = int(request.args.get("page", 1))
    num = min(int(request.args.get("num", 1000)), 2000)

    resp = client.list_files(dir_path=dir_path, order=order, page=page, num=num)
    if resp.get("errno") != 0:
        return jsonify(ok=False, error=f"errno {resp.get('errno')}"), 500

    quota_info = client.quota()
    items = [norm_file(f) for f in resp.get("list", [])]

    return jsonify(
        ok=True,
        items=items,
        quota={"total": quota_info.get("total", 0), "used": quota_info.get("used", 0)} if quota_info else None,
    )


@files_bp.post("/op")
def file_op():
    """Operasi file: rename, move, copy, delete."""
    client, err_resp, err_code = _require_client()
    if err_resp:
        return err_resp, err_code

    body = request.get_json(silent=True) or {}
    opera = body.get("opera")
    filelist = body.get("filelist")

    if not validate_operation(opera):
        return jsonify(ok=False, error="Operasi tidak valid"), 400
    if not isinstance(filelist, list):
        return jsonify(ok=False, error="filelist harus array"), 400

    resp = client.file_op(opera, filelist)
    return jsonify(ok=resp.get("errno") == 0, errno=resp.get("errno"))


@files_bp.post("/mkdir")
def mkdir():
    """Buat folder baru."""
    client, err_resp, err_code = _require_client()
    if err_resp:
        return err_resp, err_code

    path = (request.get_json(silent=True) or {}).get("path", "")
    if not path:
        return jsonify(ok=False, error="path kosong"), 400

    resp = client.mkdir(path)
    return jsonify(ok=resp.get("errno") == 0, errno=resp.get("errno"))
