from scripts.vless_to_xray import build_config, link_name

REALITY = (
    "vless://11111111-2222-3333-4444-555555555555@example.net:443"
    "?type=tcp&security=reality&sni=www.microsoft.com&fp=chrome&pbk=PUBKEY&sid=ab12&flow=xtls-rprx-vision"
    "&encryption=none#%F0%9F%87%B3%F0%9F%87%B1%20NL"
)


def test_reality_link_to_config():
    cfg = build_config(REALITY)
    out = cfg["outbounds"][0]
    vnext = out["settings"]["vnext"][0]
    assert (vnext["address"], vnext["port"]) == ("example.net", 443)
    assert vnext["users"][0] == {"id": "11111111-2222-3333-4444-555555555555", "encryption": "none",
                                 "flow": "xtls-rprx-vision"}
    reality = out["streamSettings"]["realitySettings"]
    assert reality["publicKey"] == "PUBKEY" and reality["serverName"] == "www.microsoft.com"
    assert cfg["inbounds"][0]["port"] == 1080
    assert link_name(REALITY) == "🇳🇱 NL"


def test_ws_tls_link():
    cfg = build_config("vless://id@h.example:8443?type=ws&security=tls&path=%2Fws&host=cdn.example&sni=cdn.example#x")
    stream = cfg["outbounds"][0]["streamSettings"]
    assert stream["wsSettings"] == {"path": "/ws", "headers": {"Host": "cdn.example"}}
    assert stream["tlsSettings"]["serverName"] == "cdn.example"


def test_json_subscription_and_placeholders():
    import json

    from scripts.vless_to_xray import _address, _parse_json, _parse_links

    body = json.dumps([
        {"remarks": "🇩🇪 DE", "outbounds": [
            {"tag": "proxy", "protocol": "vless", "settings": {"vnext": [{"address": "de.example", "port": 443}]}},
            {"tag": "direct", "protocol": "freedom"}]},
        {"remarks": "Приложение не поддерживается", "outbounds": [
            {"protocol": "vless", "settings": {"vnext": [{"address": "0.0.0.0", "port": 1}]}}]},
    ])
    servers = _parse_json(body)
    assert [name for name, _ in servers] == ["🇩🇪 DE", "Приложение не поддерживается"]
    assert "tag" not in servers[0][1] and _address(servers[0][1]) == "de.example"
    assert _address(servers[1][1]) == "0.0.0.0"
    assert _parse_links(REALITY)[0][0] == "🇳🇱 NL"
