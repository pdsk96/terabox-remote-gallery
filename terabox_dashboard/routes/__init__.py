"""Routes package: register semua blueprint."""
from flask import Flask

from .auth import auth_bp
from .channels import channel_bp
from .files import files_bp
from .proxy import proxy_bp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(auth_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(proxy_bp)
    app.register_blueprint(channel_bp)
