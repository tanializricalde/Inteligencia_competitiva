from collections.abc import Callable

from apps.reviews.application.dtos import ReviewScraperAdapter

ReviewAdapterFactory = Callable[[], ReviewScraperAdapter]
_factories: dict[str, ReviewAdapterFactory] = {}


def register_review_adapter(key: str, factory: ReviewAdapterFactory) -> None:
    if not key or key in _factories:
        raise ValueError(f"Clave de adapter de reseñas inválida o duplicada: {key!r}")
    _factories[key] = factory


def get_review_adapter(key: str) -> ReviewScraperAdapter:
    try:
        return _factories[key]()
    except KeyError as exc:
        raise ValueError(f"Adapter de reseñas no registrado: {key!r}") from exc


def review_adapter_keys() -> tuple[str, ...]:
    return tuple(sorted(_factories))
