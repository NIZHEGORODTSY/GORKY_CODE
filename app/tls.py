import ssl
from functools import lru_cache


@lru_cache
def sber_ssl_context(ca_bundle: str = "") -> ssl.SSLContext:
    """Системные корневые сертификаты + сертификат Минцифры для API Сбера.

    Системное хранилище оставляем: часть хостов (api.giga.chat) подписана обычными CA,
    а антивирусы на dev-машинах подменяют сертификаты своими корневыми.
    """
    ctx = ssl.create_default_context()
    if ca_bundle:
        ctx.load_verify_locations(cafile=ca_bundle)
    return ctx
