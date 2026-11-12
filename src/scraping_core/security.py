import ipaddress
import socket
from urllib.parse import urlsplit

from .errors import UnsafeSourceUrlError


def _reject_address(value: str, *, allow_private_hosts: bool) -> None:
    address = ipaddress.ip_address(value)
    if not allow_private_hosts and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    ):
        raise UnsafeSourceUrlError("No se permiten direcciones privadas o reservadas")


def validate_source_url(
    url: str, *, allow_private_hosts: bool = False, resolve_host: bool = False
) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
        raise UnsafeSourceUrlError("La URL debe ser HTTP(S), sin credenciales y con host válido")
    hostname = parsed.hostname.casefold().rstrip(".")
    if not allow_private_hosts and (hostname == "localhost" or hostname.endswith(".localhost")):
        raise UnsafeSourceUrlError("No se permiten hosts locales")
    try:
        _reject_address(hostname, allow_private_hosts=allow_private_hosts)
        return
    except ValueError:
        if not resolve_host:
            return
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise UnsafeSourceUrlError("No fue posible resolver el host de la fuente") from exc
    for address in addresses:
        _reject_address(address, allow_private_hosts=allow_private_hosts)
