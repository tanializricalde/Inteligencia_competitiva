from collections.abc import Callable

from apps.scraping.application.dtos import ProviderScraper

Factory = Callable[[], ProviderScraper]
_factories: dict[str, Factory] = {}


def register_adapter(key: str, factory: Factory) -> None:
    if not key or key in _factories:
        raise ValueError(f"Clave de adaptador inválida o duplicada: {key!r}")
    _factories[key] = factory


def get_adapter(key: str) -> ProviderScraper:
    try:
        return _factories[key]()
    except KeyError as exc:
        raise ValueError(f"Adaptador no registrado: {key!r}") from exc


def adapter_keys() -> tuple[str, ...]:
    return tuple(sorted(_factories))
