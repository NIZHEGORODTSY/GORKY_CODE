"""Подпись initData так же, как это делает Telegram, — для тестов и локального просмотра Mini App."""

import hashlib
import hmac
import json
import time
from urllib.parse import quote, urlencode


def sign_init_data(bot_token: str, user_id: int, first_name: str = "Dev") -> str:
    fields = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": user_id, "first_name": first_name}, separators=(",", ":")),
    }
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def local_url(bot_token: str, user_id: int, base: str = "http://localhost:8080/app/") -> str:
    """Ссылка для обычного браузера: telegram-web-app.js читает initData из #tgWebAppData."""
    return f"{base}#tgWebAppData={quote(sign_init_data(bot_token, user_id))}&tgWebAppVersion=8.0&tgWebAppPlatform=web"
