"""VLESS-ссылка или подписка -> xray/config.json (SOCKS5-прокси для бота на :1080).

Нужен, если хостинг блокирует Telegram. Только стандартная библиотека — запускается на сервере:

    python3 scripts/vless_to_xray.py 'https://подписка...'      # подписка (как в Happ)
    python3 scripts/vless_to_xray.py 'vless://...'              # один сервер
    python3 scripts/vless_to_xray.py 'https://...' --list       # показать серверы подписки
    python3 scripts/vless_to_xray.py 'https://...' --index 2    # выбрать сервер по номеру

Затем в .env: TELEGRAM_PROXY=socks5://xray:1080 и ./scripts/deploy.sh.
Ссылка — секрет: не коммить её и xray/config.json (он в .gitignore).
"""

import argparse
import base64
import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

OUT = Path(__file__).resolve().parent.parent / "xray" / "config.json"
SOCKS_PORT = 1080


def fetch_links(source: str) -> list[str]:
    if source.startswith("vless://"):
        return [source]
    if source.startswith("happ://"):
        sys.exit("Зашифрованная ссылка happ:// не поддерживается — скопируй в Happ ссылку подписки (https://…) "
                 "или конфиг сервера (vless://…).")
    req = urllib.request.Request(source, headers={"User-Agent": "v2rayN/6.45"})
    body = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore").strip()
    if "vless://" not in body:
        try:
            body = base64.b64decode(body + "=" * (-len(body) % 4)).decode("utf-8", "ignore")
        except ValueError:
            pass
    links = [line.strip() for line in body.splitlines() if line.strip().startswith("vless://")]
    if not links:
        sys.exit("В подписке не нашлось серверов VLESS.")
    return links


def link_name(link: str) -> str:
    return unquote(urlsplit(link).fragment) or urlsplit(link).hostname or "?"


def build_config(link: str) -> dict:
    u = urlsplit(link)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    network = q.get("type", "tcp")
    security = q.get("security", "none")

    user = {"id": unquote(u.username or ""), "encryption": q.get("encryption", "none")}
    if q.get("flow"):
        user["flow"] = q["flow"]

    stream: dict = {"network": network, "security": security}
    if security == "reality":
        stream["realitySettings"] = {
            "serverName": q.get("sni", ""),
            "fingerprint": q.get("fp", "chrome"),
            "publicKey": q.get("pbk", ""),
            "shortId": q.get("sid", ""),
            "spiderX": unquote(q.get("spx", "")),
        }
    elif security == "tls":
        tls = {"serverName": q.get("sni", u.hostname), "fingerprint": q.get("fp", "chrome")}
        if q.get("alpn"):
            tls["alpn"] = unquote(q["alpn"]).split(",")
        stream["tlsSettings"] = tls
    if network == "ws":
        stream["wsSettings"] = {"path": unquote(q.get("path", "/")), "headers": {"Host": q.get("host", "")}}
    elif network == "grpc":
        stream["grpcSettings"] = {"serviceName": unquote(q.get("serviceName", ""))}
    elif network in ("xhttp", "splithttp"):
        stream["network"] = "xhttp"
        stream["xhttpSettings"] = {"path": unquote(q.get("path", "/")), "host": q.get("host", ""),
                                   "mode": q.get("mode", "auto")}

    return {
        "log": {"loglevel": "warning"},
        "inbounds": [{"listen": "0.0.0.0", "port": SOCKS_PORT, "protocol": "socks", "settings": {"udp": False}}],
        "outbounds": [{
            "protocol": "vless",
            "settings": {"vnext": [{"address": u.hostname, "port": u.port or 443, "users": [user]}]},
            "streamSettings": stream,
        }],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="ссылка подписки https://… или vless://…")
    parser.add_argument("--index", type=int, default=1, help="номер сервера из подписки (с 1)")
    parser.add_argument("--list", action="store_true", help="только показать серверы")
    args = parser.parse_args()

    links = fetch_links(args.source)
    if args.list:
        for i, link in enumerate(links, 1):
            print(f"{i}. {link_name(link)}")
        return
    link = links[args.index - 1]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(build_config(link), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Готово: {OUT} (сервер «{link_name(link)}»). Теперь в .env: TELEGRAM_PROXY=socks5://xray:{SOCKS_PORT}")


if __name__ == "__main__":
    main()
