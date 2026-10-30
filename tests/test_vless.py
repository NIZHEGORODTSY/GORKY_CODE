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
