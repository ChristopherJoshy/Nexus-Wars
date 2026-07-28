import json
import os

import firebase_admin
from firebase_admin import auth, credentials

_app: firebase_admin.App | None = None


def get_firebase_app() -> firebase_admin.App:
    global _app
    if _app is not None:
        return _app

    path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_PATH")
    inline = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")

    if inline:
        cred = credentials.Certificate(json.loads(inline))
    elif path:
        cred = credentials.Certificate(path)
    else:
        raise RuntimeError(
            "Set FIREBASE_SERVICE_ACCOUNT_PATH or FIREBASE_SERVICE_ACCOUNT_JSON"
        )

    _app = firebase_admin.initialize_app(cred)
    return _app


def verify_token(id_token: str) -> dict:
    app = get_firebase_app()
    decoded = auth.verify_id_token(id_token, app=app)
    return decoded
