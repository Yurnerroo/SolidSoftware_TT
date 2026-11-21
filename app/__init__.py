from flask import Flask

from app.config import Config
from app.extensions import db
from app.payment_provider import MockPaymentProvider
from app.routes import bp


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config.update(config or {})

    db.init_app(app)
    app.extensions["payment_provider"] = MockPaymentProvider()
    app.register_blueprint(bp)
    return app
