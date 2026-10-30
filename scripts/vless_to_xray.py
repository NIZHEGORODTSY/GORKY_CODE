"""VLESS-ссылка или подписка -> xray/config.json (SOCKS5-прокси для бота на :1080).

Нужен, если хостинг блокирует Telegram. Только стандартная библиотека — запускается на сервере:

    python3 scripts/vless_to_xray.py 'https://подписка...' --list   # показать серверы подписки
    python3 scripts/vless_to_xray.py 'https://подписка...' --index 2 # выбрать сервер по номеру
    python3 scripts/vless_to_xray.py 'vless://...'                   # один сервер

Подписку запрашиваем как приложение Happ и с HWID этого сервера (из /etc/machine-id): многие VPN
отдают серверы только «своим» приложениям и считают устройства по HWID — сервер займёт одно место.

Затем в .env: TELEGRAM_PROXY=socks5://xray:1080 и ./scripts/deploy.sh.
Ссылка — секрет: не коммить её и xray/config.json (он в .gitignore).
"""

import argparse
import base64
import hashlib
import json
import sys
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "xray" / "config.json"
SOCKS_PORT = 1080
USER_AGENT = "Happ/3.6.0"
PROXY_PROTOCOLS = {"vless", "vmess", "trojan", "shadowsocks"}
PLACEHOLDER_HOSTS = {"0.0.0.0", "127.0.0.1", "localhost", ""}


def device_id() -> str:
    """Стабильный HWID сервера: одно и то же «устройство» при каждом запуске."""
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        p = Path(path)
        if p.exists() and p.read_text().strip():
            return hashlib.sha256(p.read_text().strip().encode()).hexdigest()[:32]
    saved = ROOT / "xray" / "hwid"
    if not saved.exists():
        saved.parent.mkdir(exist_ok=True)
        saved.write_text(uuid.uuid4().hex)
    return saved.read_text().strip()


def fetch_servers(source: str) -> list[tuple[str, dict]]:
    """[(название, outbound xray)] из ссылки vless:// или подписки https://."""
    if source.startswith("vless://"):
        return [(link_name(source), build_outbound(source))]
    if source.startswith("happ://"):
        sys.exit("Зашифрованная ссылка happ:// не поддерживается — нужна ссылка подписки https://… "
                 "или конфиг сервера vless://…")
    headers = {
        "User-Agent": USER_AGENT,
        "x-hwid": device_id(),
        "x-device-os": "Linux",
        "x-ver-os": "22.04",
        "x-device-model": "GORKY VPS",
    }
    body = urllib.request.urlopen(urllib.request.Request(source, headers=headers), timeout=20)
    body = body.read().decode("utf-8", "ignore").strip()
    servers = _parse_json(body) if body[:1] in "[{" else _parse_links(body)
    real = [(name, ob) for name, ob in servers if _address(ob) not in PLACEHOLDER_HOSTS]
    if not real:
        names = "; ".join(name for name, _ in servers) or "пусто"
        sys.exit(f"Подписка не отдала настоящих серверов (ответ: {names}).\n"
                 "Скорее всего, исчерпан лимит устройств (HWID) — удали лишнее устройство в личном кабинете VPN "
                 "или скопируй в приложении конфиг одного сервера (vless://…) и передай его скрипту.")
    return real


def _parse_links(body: str) -> list[tuple[str, dict]]:
    if "://" not in body:
        try:
            body = base64.b64decode(body + "=" * (-len(body) % 4)).decode("utf-8", "ignore")
        except ValueError:
            pass
    links = [line.strip() for line in body.splitlines() if line.strip().startswith("vless://")]
    return [(link_name(link), build_outbound(link)) for link in links]


def _parse_json(body: str) -> list[tuple[str, dict]]:
    """Подписка в формате готовых конфигов xray (так её получает Happ)."""
    data = json.loads(body)
    configs = data if isinstance(data, list) else [data]
    servers = []
    for cfg in configs:
        for ob in cfg.get("outbounds", []):
            if ob.get("protocol") in PROXY_PROTOCOLS:
                servers.append((cfg.get("remarks", "?"), {k: v for k, v in ob.items() if k != "tag"}))
                break
    return servers


def _address(outbound: dict) -> str:
    settings = outbound.get("settings", {})
    for key in ("vnext", "servers"):
        if settings.get(key):
            return settings[key][0].get("address", "")
    return ""


def link_name(link: str) -> str:
    return unquote(urlsplit(link).fragment) or urlsplit(link).hostname or "?"


def build_outbound(link: str) -> dict:
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
        "protocol": "vless",
        "settings": {"vnext": [{"address": u.hostname, "port": u.port or 443, "users": [user]}]},
        "streamSettings": stream,
    }


def build_config(outbound_or_link: dict | str) -> dict:
    outbound = build_outbound(outbound_or_link) if isinstance(outbound_or_link, str) else outbound_or_link
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [{"listen": "0.0.0.0", "port": SOCKS_PORT, "protocol": "socks", "settings": {"udp": False}}],
        "outbounds": [outbound],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="ссылка подписки https://… или vless://…")
    parser.add_argument("--index", type=int, default=1, help="номер сервера из подписки (с 1)")
    parser.add_argument("--list", action="store_true", help="только показать серверы")
    args = parser.parse_args()

    servers = fetch_servers(args.source)
    if args.list:
        for i, (name, ob) in enumerate(servers, 1):
            print(f"{i}. {name} ({ob.get('protocol')})")
        return
    name, outbound = servers[args.index - 1]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(build_config(outbound), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Готово: {OUT} (сервер «{name}»). Теперь в .env: TELEGRAM_PROXY=socks5://xray:{SOCKS_PORT}")


if __name__ == "__main__":
    main()
