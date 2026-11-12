from __future__ import annotations

import colorsys
import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode

from django.db.models import Prefetch, Q
from django.http import QueryDict
from django.utils import timezone

from apps.pipeline.application.queries import latest_published_provider_runs
from apps.pipeline.models import (
    FeatureDefinition,
    MarketPlan,
    PlanFeatureValue,
    PlanPriceSnapshot,
    PlanSnapshot,
    ReviewSnapshot,
)

from .models import DashboardPreset, DashboardSettings, Provider

PERIOD_OPTIONS = ((3, "Últimos 3 meses"), (6, "Últimos 6 meses"), (12, "Últimos 12 meses"))
PERIOD_DAYS = {3: 90, 6: 183, 12: 366}
MAX_PROVIDER_FILTERS = 20
MAX_PLAN_FILTERS = 100
MAX_FEATURE_FILTERS = 300
PROVIDER_COLORS = (
    "#E69F00",  # naranja
    "#56B4E9",  # azul cielo
    "#009E73",  # verde azulado
    "#F0E442",  # amarillo
    "#0072B2",  # azul
    "#D55E00",  # bermellón
    "#CC79A7",  # rosa rojizo
    "#000000",  # negro
)
CHROMATIC_PROVIDER_COLORS = PROVIDER_COLORS[:-1]
GOLDEN_ANGLE = 137.50776405003785


class DashboardSelectionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DashboardSelection:
    preset: DashboardPreset
    providers: tuple[Provider, ...]
    plans: tuple[MarketPlan, ...]
    available_providers: tuple[Provider, ...]
    available_plans: tuple[MarketPlan, ...]
    features: tuple[FeatureDefinition, ...]
    available_features: tuple[FeatureDefinition, ...]
    period_months: int
    feature_filter_active: bool
    temporary_filters: bool
    warnings: tuple[str, ...] = ()
    notices: tuple[str, ...] = ()
    canonical_query: str = ""
    feature_reset_query: str = ""

    @property
    def scope(self) -> str:
        return self.preset.data_scope


def provider_color(code: str) -> str:
    """Return a deterministic chromatic anchor from the Okabe-Ito palette."""
    digest = hashlib.sha256(code.encode("utf-8")).digest()
    return CHROMATIC_PROVIDER_COLORS[
        int.from_bytes(digest[:2], "big") % len(CHROMATIC_PROVIDER_COLORS)
    ]


def provider_color_map(codes: tuple[str, ...]) -> dict[str, str]:
    """Assign deterministic colors using maximin perceptual distance in OKLab."""
    unique_codes = tuple(dict.fromkeys(codes))
    assigned: dict[str, str] = {}
    used_colors: list[str] = []
    primary_candidates = list(PROVIDER_COLORS)
    generated_candidates = _generated_provider_candidates(max(96, len(unique_codes) * 12))
    for code in sorted(unique_codes):
        if not used_colors:
            selected = provider_color(code)
        elif primary_candidates:
            selected = _maximin_color(code, primary_candidates, used_colors)
        else:
            available = tuple(color for color in generated_candidates if color not in used_colors)
            selected = _maximin_color(code, available, used_colors)
        assigned[code] = selected
        used_colors.append(selected)
        if selected in primary_candidates:
            primary_candidates.remove(selected)
    return assigned


def _maximin_color(code: str, candidates: tuple[str, ...] | list[str], used: list[str]) -> str:
    def score(candidate: str) -> tuple[float, int]:
        minimum_distance = min(_oklab_distance(candidate, color) for color in used)
        tie_breaker = int.from_bytes(
            hashlib.sha256(f"{code}:{candidate}".encode()).digest()[:4], "big"
        )
        return minimum_distance, tie_breaker

    return max(candidates, key=score)


def _generated_provider_candidates(count: int) -> tuple[str, ...]:
    colors: list[str] = []
    for index in range(count):
        hue = ((index * GOLDEN_ANGLE + 17) % 360) / 360
        saturation = (0.68, 0.78, 0.73)[index % 3]
        lightness = (0.43, 0.55, 0.49)[(index // 3) % 3]
        red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
        color = f"#{round(red * 255):02X}{round(green * 255):02X}{round(blue * 255):02X}"
        if color not in PROVIDER_COLORS and color not in colors:
            colors.append(color)
    return tuple(colors)


@lru_cache(maxsize=512)
def _hex_to_oklab(color: str) -> tuple[float, float, float]:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    red, green, blue = (
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    )
    light = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    medium = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    short = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue
    light_root = light ** (1 / 3)
    medium_root = medium ** (1 / 3)
    short_root = short ** (1 / 3)
    return (
        0.2104542553 * light_root + 0.793617785 * medium_root - 0.0040720468 * short_root,
        1.9779984951 * light_root - 2.428592205 * medium_root + 0.4505937099 * short_root,
        0.0259040371 * light_root + 0.7827717662 * medium_root - 0.808675766 * short_root,
    )


def _oklab_distance(first: str, second: str) -> float:
    return math.dist(_hex_to_oklab(first), _hex_to_oklab(second))


def resolve_dashboard_selection(params: QueryDict, *, strict: bool = True) -> DashboardSelection:
    settings = DashboardSettings.load()
    warnings: list[str] = []
    notices: list[str] = []
    requested_slug = params.get("preset", "").strip()
    if len(requested_slug) > 100:
        _selection_issue(strict, warnings, "El identificador de la vista es demasiado largo")
        requested_slug = ""
    if requested_slug:
        preset = DashboardPreset.objects.filter(slug=requested_slug, is_active=True).first()
        if preset is None:
            _selection_issue(strict, warnings, "La vista solicitada no existe o está inactiva")
            preset = _default_preset(settings)
    else:
        preset = _default_preset(settings)

    raw_period = params.get("period", "6")
    try:
        period_months = int(raw_period)
    except (TypeError, ValueError):
        _selection_issue(strict, warnings, "El periodo debe ser 3, 6 o 12 meses")
        period_months = 6
    if period_months not in PERIOD_DAYS:
        _selection_issue(strict, warnings, "El periodo debe ser 3, 6 o 12 meses")
        period_months = 6

    current_runs = latest_published_provider_runs(data_scope=preset.data_scope).filter(
        provider__is_active=True
    )
    published_provider_ids = set(current_runs.values_list("provider_id", flat=True))
    providers = Provider.objects.filter(
        id__in=published_provider_ids,
        is_active=True,
        data_scope=preset.data_scope,
    )
    if not preset.is_system:
        providers = providers.filter(dashboardpresetprovider__preset=preset)
    providers = tuple(providers.order_by("execution_order", "name", "id"))
    provider_ids = {provider.id for provider in providers}
    current_run_ids = set(
        current_runs.filter(provider_id__in=provider_ids).values_list("id", flat=True)
    )
    plans = MarketPlan.objects.filter(
        provider_id__in=provider_ids,
        is_active=True,
        snapshots__provider_run_id__in=current_run_ids,
    )
    if preset.plan_selection == DashboardPreset.PlanSelection.EXPLICIT:
        plans = plans.filter(dashboardpresetplan__preset=preset)
    plans = tuple(plans.select_related("provider").distinct().order_by("provider", "external_key"))
    plan_names = dict(
        PlanSnapshot.objects.filter(
            provider_run_id__in=current_run_ids,
            market_plan_id__in=[plan.id for plan in plans],
        ).values_list("market_plan_id", "plan_name")
    )
    for plan in plans:
        plan.dashboard_name = plan_names.get(plan.id, plan.external_key)
    available_providers = providers
    available_plans = plans

    raw_provider_codes = _bounded_values(
        params, "provider", MAX_PROVIDER_FILTERS, "competidores", strict, warnings
    )
    raw_plan_ids = _bounded_values(params, "plan", MAX_PLAN_FILTERS, "planes", strict, warnings)
    applied_provider_codes: tuple[str, ...] = ()
    applied_plan_ids: tuple[int, ...] = ()
    if raw_provider_codes:
        available_codes = {provider.code for provider in providers}
        valid_codes = tuple(code for code in raw_provider_codes if code in available_codes)
        if len(valid_codes) != len(raw_provider_codes):
            _selection_issue(
                strict, warnings, "Se descartaron competidores que no pertenecen a la vista"
            )
        if valid_codes:
            applied_provider_codes = valid_codes
            providers = tuple(provider for provider in providers if provider.code in valid_codes)
            provider_ids = {provider.id for provider in providers}
            plans = tuple(plan for plan in plans if plan.provider_id in provider_ids)
    if raw_plan_ids:
        numeric_ids = tuple(int(value) for value in raw_plan_ids if value.isdigit())
        if len(numeric_ids) != len(raw_plan_ids):
            _selection_issue(strict, warnings, "Se descartaron identificadores de plan inválidos")
        available_plan_ids = {plan.id for plan in plans}
        valid_plan_ids = tuple(value for value in numeric_ids if value in available_plan_ids)
        if len(valid_plan_ids) != len(numeric_ids):
            _selection_issue(strict, warnings, "Se descartaron planes que no pertenecen a la vista")
        if valid_plan_ids:
            applied_plan_ids = valid_plan_ids
            plans = tuple(plan for plan in plans if plan.id in valid_plan_ids)
            if not applied_provider_codes:
                provider_ids = {plan.provider_id for plan in plans}
                providers = tuple(provider for provider in providers if provider.id in provider_ids)

    selected_plan_ids = tuple(plan.id for plan in plans)
    selected_provider_ids = tuple(provider.id for provider in providers)
    available_features = tuple(
        FeatureDefinition.objects.filter(
            is_active=True,
            scope=FeatureDefinition.Scope.CANONICAL,
            values__plan_snapshot__provider_run_id__in=current_run_ids,
            values__plan_snapshot__provider_run__provider_id__in=selected_provider_ids,
            values__plan_snapshot__market_plan_id__in=selected_plan_ids,
        )
        .distinct()
        .order_by("category", "display_name", "code", "id")
    )
    evidenced_feature_ids = set(
        PlanFeatureValue.objects.filter(
            feature_definition__is_active=True,
            feature_definition__scope=FeatureDefinition.Scope.CANONICAL,
            plan_snapshot__provider_run_id__in=current_run_ids,
            plan_snapshot__provider_run__provider_id__in=selected_provider_ids,
            plan_snapshot__market_plan_id__in=selected_plan_ids,
        )
        .exclude(availability=PlanFeatureValue.Availability.UNKNOWN)
        .values_list("feature_definition_id", flat=True)
        .distinct()
    )
    features = tuple(
        feature for feature in available_features if feature.id in evidenced_feature_ids
    )
    if preset.feature_selection == DashboardPreset.FeatureSelection.EXPLICIT:
        configured_ids = set(
            preset.dashboardpresetfeature_set.values_list("feature_definition_id", flat=True)
        )
        available_ids = {feature.id for feature in available_features}
        features = tuple(feature for feature in available_features if feature.id in configured_ids)
        if configured_ids - available_ids:
            notices.append("Algunas características guardadas ya no están disponibles")

    raw_feature_codes = _bounded_values(
        params, "feature", MAX_FEATURE_FILTERS, "características", strict, warnings
    )
    marker = params.get("feature_filter", "").strip()
    if marker not in {"", "1"}:
        _selection_issue(strict, warnings, "El filtro de características es inválido")
    feature_filter_active = marker == "1" or bool(raw_feature_codes)
    applied_feature_codes: tuple[str, ...] = ()
    if feature_filter_active:
        available_codes = {feature.code for feature in available_features}
        valid_codes = tuple(code for code in raw_feature_codes if code in available_codes)
        if len(valid_codes) != len(raw_feature_codes):
            _selection_issue(
                strict,
                warnings,
                "Se descartaron características que no pertenecen a la vista",
            )
        applied_feature_codes = valid_codes
        features = tuple(feature for feature in available_features if feature.code in valid_codes)

    canonical_items: list[tuple[str, str | int]] = [
        ("preset", preset.slug),
        ("period", period_months),
    ]
    canonical_items.extend(("provider", code) for code in applied_provider_codes)
    canonical_items.extend(("plan", plan_id) for plan_id in applied_plan_ids)
    feature_reset_query = urlencode(canonical_items)
    if feature_filter_active:
        canonical_items.append(("feature_filter", "1"))
        canonical_items.extend(("feature", code) for code in applied_feature_codes)

    return DashboardSelection(
        preset=preset,
        providers=providers,
        plans=plans,
        available_providers=available_providers,
        available_plans=available_plans,
        features=features,
        available_features=available_features,
        period_months=period_months,
        feature_filter_active=feature_filter_active,
        temporary_filters=bool(applied_provider_codes or applied_plan_ids or feature_filter_active),
        warnings=tuple(dict.fromkeys(warnings)),
        notices=tuple(dict.fromkeys(notices)),
        canonical_query=urlencode(canonical_items),
        feature_reset_query=feature_reset_query,
    )


def _default_preset(settings: DashboardSettings) -> DashboardPreset:
    if settings.default_preset_id and settings.default_preset.is_active:
        return settings.default_preset
    return DashboardPreset.objects.get(slug=DashboardPreset.SYSTEM_ALL_SLUG, is_active=True)


def _selection_issue(strict: bool, warnings: list[str], message: str) -> None:
    if strict:
        raise DashboardSelectionError(message)
    warnings.append(message)


def _bounded_values(
    params: QueryDict,
    key: str,
    limit: int,
    label: str,
    strict: bool,
    warnings: list[str],
) -> tuple[str, ...]:
    values = tuple(dict.fromkeys(value.strip() for value in params.getlist(key) if value.strip()))
    if len(values) > limit or sum(len(value) for value in values) > 4000:
        _selection_issue(strict, warnings, f"La selección contiene demasiados {label}")
        return ()
    return values


def build_dashboard_data(selection: DashboardSelection) -> dict[str, Any]:
    provider_ids = tuple(provider.id for provider in selection.providers)
    plan_ids = tuple(plan.id for plan in selection.plans)
    current_runs = list(
        latest_published_provider_runs(data_scope=selection.scope).filter(
            provider_id__in=provider_ids
        )
    )
    current_run_ids = tuple(run.id for run in current_runs)
    current_snapshots = list(
        PlanSnapshot.objects.filter(
            provider_run_id__in=current_run_ids,
            market_plan_id__in=plan_ids,
            market_plan__is_active=True,
        )
        .select_related("market_plan", "provider_run__provider")
        .prefetch_related(
            Prefetch("prices", queryset=PlanPriceSnapshot.objects.filter(source_kind="scraped")),
            Prefetch(
                "feature_values",
                queryset=PlanFeatureValue.objects.select_related("feature_definition").filter(
                    feature_definition__is_active=True,
                    feature_definition__scope="canonical",
                ),
            ),
        )
        .order_by("provider_run__provider__execution_order", "plan_name", "id")
    )
    cutoff = timezone.now() - timedelta(days=PERIOD_DAYS[selection.period_months])
    reviews = list(
        ReviewSnapshot.objects.filter(
            provider_run_id__in=current_run_ids,
            market_review__provider_id__in=provider_ids,
        )
        .filter(
            Q(review_published_at__gte=cutoff)
            | Q(review_published_at__isnull=True, ingested_at__gte=cutoff)
        )
        .select_related("provider_run__provider", "market_review")
    )
    provider_colors = provider_color_map(tuple(provider.code for provider in selection.providers))
    return {
        "providers": _provider_payload(selection.providers, provider_colors),
        "cutoffs": [
            {
                "provider": run.provider.name,
                "published_at": run.published_at,
            }
            for run in current_runs
        ],
        "heatmap": _heatmap(selection.providers, selection.features, current_snapshots),
        "price_evolution": _price_evolution(selection, cutoff, provider_colors),
        "price_rating": _price_rating(
            selection.providers, current_snapshots, reviews, provider_colors
        ),
        "sentiment": _sentiment(selection.providers, reviews),
        "plans": _plan_cards(selection.providers, current_snapshots, provider_colors),
    }


def build_comparison_data(
    selection: DashboardSelection, *, use_default_limit: bool = False
) -> dict[str, Any]:
    plans = selection.plans[:4] if use_default_limit else selection.plans
    plan_ids = tuple(plan.id for plan in plans)
    current_run_ids = (
        latest_published_provider_runs(data_scope=selection.scope)
        .filter(provider_id__in=[provider.id for provider in selection.providers])
        .values("id")
    )
    snapshots = list(
        PlanSnapshot.objects.filter(
            provider_run_id__in=current_run_ids,
            market_plan_id__in=plan_ids,
            market_plan__is_active=True,
        )
        .select_related("market_plan__provider", "provider_run__provider")
        .prefetch_related(
            Prefetch("prices", queryset=PlanPriceSnapshot.objects.filter(source_kind="scraped")),
            Prefetch(
                "feature_values",
                queryset=PlanFeatureValue.objects.select_related("feature_definition").filter(
                    feature_definition_id__in=[feature.id for feature in selection.features]
                ),
            ),
        )
        .order_by("market_plan__provider__execution_order", "plan_name", "id")
    )
    snapshots_by_plan = {snapshot.market_plan_id: snapshot for snapshot in snapshots}
    columns = []
    for plan in plans:
        snapshot = snapshots_by_plan.get(plan.id)
        prices = []
        if snapshot is not None:
            prices = [
                {
                    "period": price.get_billing_period_display(),
                    "currency": price.currency_code,
                    "amount": price.amount,
                }
                for price in snapshot.prices.all()
            ]
        columns.append(
            {
                "id": plan.id,
                "provider": plan.provider.name,
                "name": snapshot.plan_name if snapshot else plan.external_key,
                "product": snapshot.product_code if snapshot else "",
                "observed_at": snapshot.observed_at if snapshot else None,
                "prices": prices,
                "snapshot": snapshot,
            }
        )
    rows = []
    for definition in selection.features:
        cells = []
        for column in columns:
            snapshot = column["snapshot"]
            value = None
            if snapshot is not None:
                value = next(
                    (
                        candidate
                        for candidate in snapshot.feature_values.all()
                        if candidate.feature_definition_id == definition.id
                    ),
                    None,
                )
            state = _feature_state(value)
            full_value = _format_feature_value(definition, value) or _empty_value(state)
            cells.append(
                {
                    "state": state,
                    "state_label": _feature_state_label(state),
                    "value": full_value,
                }
            )
        signatures = {(cell["state"], cell["value"]) for cell in cells}
        if any(cell["state"] != "unknown" for cell in cells):
            rows.append(
                {
                    "code": definition.code,
                    "label": definition.display_name,
                    "unit": definition.unit,
                    "cells": cells,
                    "differs": len(signatures) > 1,
                }
            )
    for column in columns:
        column.pop("snapshot", None)
    return {"columns": columns, "rows": rows}


def _provider_payload(
    providers: tuple[Provider, ...], provider_colors: dict[str, str]
) -> list[dict[str, str]]:
    return [
        {
            "code": provider.code,
            "name": provider.name,
            "color": provider_colors[provider.code],
        }
        for provider in providers
    ]


def _heatmap(
    providers: tuple[Provider, ...],
    selected_features: tuple[FeatureDefinition, ...],
    snapshots: list[PlanSnapshot],
) -> dict[str, Any]:
    snapshots_by_provider: dict[int, list[PlanSnapshot]] = defaultdict(list)
    for snapshot in snapshots:
        snapshots_by_provider[snapshot.provider_run.provider_id].append(snapshot)
    rows = []
    for definition in selected_features:
        cells = []
        for provider in providers:
            provider_snapshots = snapshots_by_provider[provider.id]
            states = []
            formatted_values: list[str] = []
            plan_details: list[str] = []
            for snapshot in provider_snapshots:
                value = next(
                    (
                        item
                        for item in snapshot.feature_values.all()
                        if item.feature_definition_id == definition.id
                    ),
                    None,
                )
                plan_state = _feature_state(value)
                states.append(plan_state)
                formatted = _format_feature_value(definition, value)
                if formatted is not None and formatted not in formatted_values:
                    formatted_values.append(formatted)
                plan_value = formatted if formatted is not None else _empty_value(plan_state)
                plan_details.append(f"{_plan_detail_label(snapshot)}: {plan_value}")
            formatted_values = _order_aggregate_values(definition, formatted_values)
            state = _reduce_feature_states(states)
            full_value = " · ".join(formatted_values) if formatted_values else _empty_value(state)
            display_value = f"{full_value[:27]}…" if len(full_value) > 28 else full_value
            state_label = _feature_state_label(state)
            detail = "\n".join(plan_details) if plan_details else "Sin planes seleccionados"
            cells.append(
                {
                    "provider": provider.code,
                    "label": provider.name,
                    "state": state,
                    "state_label": state_label,
                    "value": display_value,
                    "full_value": full_value,
                    "detail": detail,
                    "aria_label": (
                        f"{provider.name}, {definition.display_name}: "
                        f"{state_label}; valor {full_value}; detalle por plan: "
                        f"{'; '.join(plan_details) if plan_details else 'sin planes seleccionados'}"
                    ),
                }
            )
        rows.append(
            {
                "code": definition.code,
                "label": definition.display_name,
                "data_type": definition.data_type,
                "unit": definition.unit,
                "cells": cells,
            }
        )
    return {
        "rows": rows,
        "legend": ("supported", "limited", "unsupported", "not_applicable", "unknown"),
    }


def _plan_detail_label(snapshot: PlanSnapshot) -> str:
    if snapshot.product_code:
        return f"{snapshot.plan_name} ({snapshot.product_code})"
    return snapshot.plan_name


def _order_aggregate_values(definition: FeatureDefinition, values: list[str]) -> list[str]:
    if definition.data_type != FeatureDefinition.DataType.BOOLEAN:
        return values
    preferred = [value for value in ("Sí", "No") if value in values]
    return preferred + [value for value in values if value not in {"Sí", "No"}]


def _feature_state(value: PlanFeatureValue | None) -> str:
    if value is None or value.availability == "unknown":
        return "unknown"
    if value.availability == "not_applicable":
        return "not_applicable"
    if value.availability == "excluded" or value.value_boolean is False:
        return "unsupported"
    if value.availability == "present":
        return "supported"
    return "unknown"


def _reduce_feature_states(states: list[str]) -> str:
    if states and all(state == "not_applicable" for state in states):
        return "not_applicable"
    known = [state for state in states if state != "unknown"]
    if not known:
        return "unknown"
    if len(known) == len(states) and all(state == "supported" for state in known):
        return "supported"
    if len(known) == len(states) and all(state == "unsupported" for state in known):
        return "unsupported"
    return "limited"


def _format_feature_value(
    definition: FeatureDefinition, value: PlanFeatureValue | None
) -> str | None:
    if value is None or value.availability in {"unknown", "not_applicable"}:
        return None
    typed = {
        FeatureDefinition.DataType.BOOLEAN: value.value_boolean,
        FeatureDefinition.DataType.INTEGER: value.value_integer,
        FeatureDefinition.DataType.DECIMAL: value.value_decimal,
        FeatureDefinition.DataType.STRING: value.value_text,
        FeatureDefinition.DataType.STRING_LIST: value.value_json,
    }[definition.data_type]
    if typed is None:
        return None
    if definition.data_type == FeatureDefinition.DataType.BOOLEAN:
        return "Sí" if typed else "No"
    if definition.data_type == FeatureDefinition.DataType.DECIMAL:
        typed = format(typed, "f").rstrip("0").rstrip(".") or "0"
    elif definition.data_type == FeatureDefinition.DataType.STRING_LIST:
        typed = ", ".join(str(item) for item in typed)
    else:
        typed = str(typed)
    unit = (definition.unit or "").strip()
    if not unit:
        return typed
    if unit == "%":
        return f"{typed} %"
    if len(unit) == 3 and unit.isalpha() and unit.upper() == unit:
        return f"{unit} {typed}"
    return f"{typed} {unit}"


def _empty_value(state: str) -> str:
    if state == "not_applicable":
        return "No aplica"
    if state == "unsupported":
        return "No compatible"
    return "Sin datos"


def _feature_state_label(state: str) -> str:
    return {
        "supported": "Compatible",
        "limited": "Parcial",
        "unsupported": "No compatible",
        "not_applicable": "No aplica",
        "unknown": "Sin datos",
    }[state]


def _price_evolution(
    selection: DashboardSelection, cutoff, provider_colors: dict[str, str]
) -> dict[str, Any]:
    snapshots = list(
        PlanSnapshot.objects.filter(
            market_plan_id__in=[plan.id for plan in selection.plans],
            provider_run__status="published",
            provider_run__published_at__gte=cutoff,
            provider_run__provider__data_scope=selection.scope,
        )
        .select_related("market_plan", "provider_run__provider")
        .prefetch_related(
            Prefetch("prices", queryset=PlanPriceSnapshot.objects.filter(source_kind="scraped"))
        )
        .order_by("provider_run__published_at", "id")
    )
    grouped: dict[tuple[str, str, str], list[Decimal]] = defaultdict(list)
    provider_names = {provider.code: provider.name for provider in selection.providers}
    for snapshot in snapshots:
        for currency, amount in _monthly_effective_prices(snapshot).items():
            date = snapshot.provider_run.published_at.date().isoformat()
            grouped[(snapshot.provider_run.provider.code, currency, date)].append(amount)
    labels = sorted({key[2] for key in grouped})
    series_keys = sorted({(key[0], key[1]) for key in grouped})
    datasets = []
    for provider_code, currency in series_keys:
        values_by_date = {
            date: _mean_decimal(amounts)
            for (code, current_currency, date), amounts in grouped.items()
            if code == provider_code and current_currency == currency
        }
        datasets.append(
            {
                "label": f"{provider_names[provider_code]} · {currency}",
                "provider": provider_code,
                "currency": currency,
                "color": provider_colors[provider_code],
                "values": [
                    float(values_by_date[label]) if label in values_by_date else None
                    for label in labels
                ],
            }
        )
    return {"labels": labels, "datasets": datasets}


def _monthly_effective_prices(snapshot: PlanSnapshot) -> dict[str, Decimal]:
    monthly = {
        price.currency_code: price.amount
        for price in snapshot.prices.all()
        if price.billing_period == "monthly"
    }
    for price in snapshot.prices.all():
        if (
            price.billing_period == "annual"
            and price.effective_monthly_amount is not None
            and price.currency_code not in monthly
        ):
            monthly[price.currency_code] = price.effective_monthly_amount
    return monthly


def _mean_decimal(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))


def _price_rating(
    providers: tuple[Provider, ...],
    snapshots: list[PlanSnapshot],
    reviews: list[ReviewSnapshot],
    provider_colors: dict[str, str],
) -> dict[str, Any]:
    prices: dict[tuple[int, str], list[Decimal]] = defaultdict(list)
    for snapshot in snapshots:
        for currency, amount in _monthly_effective_prices(snapshot).items():
            prices[(snapshot.provider_run.provider_id, currency)].append(amount)
    ratings: dict[int, list[int]] = defaultdict(list)
    for review in reviews:
        if review.rating_stars is not None:
            ratings[review.provider_run.provider_id].append(review.rating_stars)
    points = []
    for provider in providers:
        provider_ratings = ratings[provider.id]
        if not provider_ratings:
            continue
        average_rating = Decimal(sum(provider_ratings)) / Decimal(len(provider_ratings))
        for (provider_id, currency), values in prices.items():
            if provider_id != provider.id:
                continue
            points.append(
                {
                    "provider": provider.code,
                    "label": provider.name,
                    "currency": currency,
                    "x": float(_mean_decimal(values)),
                    "y": float(average_rating),
                    "reviews": len(provider_ratings),
                    "radius": min(26, max(6, 5 + len(provider_ratings) ** 0.5 * 2.5)),
                    "color": provider_colors[provider.code],
                }
            )
    return {"points": points}


def _sentiment(providers: tuple[Provider, ...], reviews: list[ReviewSnapshot]) -> dict[str, Any]:
    counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for review in reviews:
        sentiment = review.sentiment_from_rating
        if sentiment in {"positive", "neutral", "negative"}:
            counts[review.provider_run.provider_id][sentiment] += 1
        else:
            counts[review.provider_run.provider_id]["unclassified"] += 1
    rows = []
    for provider in providers:
        provider_counts = counts[provider.id]
        classified = sum(provider_counts[key] for key in ("positive", "neutral", "negative"))
        rows.append(
            {
                "provider": provider.code,
                "label": provider.name,
                "positive": _percentage(provider_counts["positive"], classified),
                "neutral": _percentage(provider_counts["neutral"], classified),
                "negative": _percentage(provider_counts["negative"], classified),
                "classified": classified,
                "unclassified": provider_counts["unclassified"],
            }
        )
    return {
        "rows": rows,
        "has_data": any(row["classified"] or row["unclassified"] for row in rows),
    }


def _percentage(value: int, total: int) -> float | None:
    return round(value * 100 / total, 2) if total else None


def _plan_cards(
    providers: tuple[Provider, ...],
    snapshots: list[PlanSnapshot],
    provider_colors: dict[str, str],
) -> list[dict[str, Any]]:
    by_provider: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for snapshot in snapshots:
        prices = [
            {
                "period": price.billing_period,
                "currency": price.currency_code,
                "amount": str(price.amount),
                "effective_monthly": (
                    str(price.effective_monthly_amount)
                    if price.effective_monthly_amount is not None
                    else None
                ),
            }
            for price in snapshot.prices.all()
            if price.billing_period in {"monthly", "annual"}
        ]
        by_provider[snapshot.provider_run.provider_id].append(
            {
                "id": snapshot.market_plan_id,
                "name": snapshot.plan_name,
                "product": snapshot.product_code,
                "prices": prices,
            }
        )
    return [
        {
            "provider": provider.code,
            "label": provider.name,
            "color": provider_colors[provider.code],
            "plans": by_provider[provider.id],
        }
        for provider in providers
    ]
