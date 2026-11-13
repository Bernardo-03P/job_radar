"""Validação única de destino local antes de transmitir chaves do projeto."""
from urllib.parse import urlsplit


def local_api_url(value=None):
    base = str(value or "http://127.0.0.1:8000").rstrip("/")
    try:
        parsed = urlsplit(base)
        port = parsed.port
    except ValueError:
        raise ValueError("Endereço do backend local inválido.") from None
    if (parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.path or (port is not None and port <= 0)):
        raise ValueError("A integração deve acessar exclusivamente a origem do backend local.")
    return base
