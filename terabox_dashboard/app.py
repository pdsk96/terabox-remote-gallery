"""Flask application factory."""
from __future__ import annotations

import logging
from typing import Optional

from flask import Flask, Response, request, session, jsonify

try:
    from .config import SETTINGS, Settings
    from .routes import register_blueprints
    from .services import init_session_store
except ImportError:
    # Direct execution: python terabox_dashboard/app.py
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from terabox_dashboard.config import SETTINGS, Settings
    from terabox_dashboard.routes import register_blueprints
    from terabox_dashboard.services import init_session_store

# ----------------------------- logging --------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("terabox_dashboard")


# ----------------------------- factory --------------------------------------
def create_app(settings: Optional[Settings] = None) -> Flask:
    """Buat instance Flask dengan konfigurasi & blueprint."""
    cfg = settings or SETTINGS

    app = Flask(__name__, template_folder="templates")
    app.config.update(
        SECRET_KEY=cfg.secret_key,
        SESSION_COOKIE_HTTPONLY=cfg.session_cookie_httponly,
        SESSION_COOKIE_SAMESITE=cfg.session_cookie_samesite,
        SESSION_COOKIE_SECURE=cfg.session_cookie_secure,
        PERMANENT_SESSION_LIFETIME=86400,
    )

    # Security headers middleware
    @app.after_request
    def add_security_headers(response: Response) -> Response:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # CSP: allow inline script (frontend) + hls.js CDN
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "media-src 'self' https:; "
            "connect-src 'self' https:; "
            "font-src 'self' data:",
        )
        return response

    # Request logging
    @app.before_request
    def log_request() -> None:
        logger.info("%s %s", request.method, request.path)

    # Load session store
    store = init_session_store(cfg)
    store.start_background_cleanup()

    # Register blueprints
    register_blueprints(app)

    # Frontend route
    @app.get("/")
    def index():
        return Response(
            app.jinja_env.get_template("index.html").render(config=cfg),
            content_type="text/html; charset=utf-8",
        )

    # Health check
    @app.get("/healthz")
    def healthz():
        return jsonify(ok=True)

    # Error handlers
    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify(ok=False, error="Unauthorized"), 401

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify(ok=False, error="Forbidden"), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify(ok=False, error="Not found"), 404

    @app.errorhandler(500)
    def internal_error(e):
        logger.exception("Internal server error")
        return jsonify(ok=False, error="Internal server error"), 500

    logger.info("TeraBox Dashboard started on %s", cfg.base_url)
    return app


# Backward compatibility: `app` instance untuk `flask run`
app = create_app()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    if args.host != "127.0.0.1":
        print(
            "PERINGATAN: dashboard ini tanpa password sendiri; siapa pun yang bisa "
            "mengakses host ini bisa login dengan cookie Anda. Gunakan jaringan tepercaya."
        )

    app.run(host=args.host, port=args.port, threaded=True, debug=SETTINGS.debug)
