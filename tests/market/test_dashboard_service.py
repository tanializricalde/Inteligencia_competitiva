from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.http import QueryDict
from django.utils import timezone

from apps.market.dashboard_service import (
    PROVIDER_COLORS,
    DashboardSelectionError,
    _oklab_distance,
    build_dashboard_data,
    provider_color_map,
    resolve_dashboard_selection,
)
from apps.market.models import (
    DashboardPreset,
    DashboardPresetPlan,
    DashboardPresetProvider,
    DashboardSettings,
    Provider,
)
from apps.pipeline.models import (
    FeatureDefinition,
    MarketPlan,
    MarketReview,
    PipelineProfile,
    PipelineProfileVersion,
    PipelineRun,
    PlanFeatureValue,
    PlanPriceSnapshot,
    PlanSnapshot,
    ProviderRun,
    ReviewSnapshot,
)


@pytest.mark.django_db
def test_all_is_dynamic_and_excludes_demo_and_unpublished_providers():
    Provider.objects.filter(data_scope=Provider.DataScope.REAL).update(is_active=False)
    first, first_plan, _ = _published_provider("real-first")
    demo = Provider.objects.filter(data_scope=Provider.DataScope.DEMO).first()

    initial = resolve_dashboard_selection(QueryDict(""))

    assert initial.preset.slug == "all"
    assert {provider.id for provider in initial.providers} == {first.id}
    assert {plan.id for plan in initial.plans} == {first_plan.id}
    assert demo.id not in {provider.id for provider in initial.providers}

    second, second_plan, _ = _published_provider("real-second")
    unpublished = Provider.objects.create(name="Sin publicar", code="unpublished")
    MarketPlan.objects.create(
        provider=unpublished,
        external_key="unpublished-plan",
        first_seen_at=timezone.now(),
        last_seen_at=timezone.now(),
    )

    refreshed = resolve_dashboard_selection(QueryDict(""))

    assert {provider.id for provider in refreshed.providers} == {first.id, second.id}
    assert {plan.id for plan in refreshed.plans} == {first_plan.id, second_plan.id}


@pytest.mark.django_db
def test_url_preset_precedes_default_and_explicit_preset_limits_each_provider():
    provider_a, plan_a, _ = _published_provider("provider-a")
    provider_b, plan_b, _ = _published_provider("provider-b")
    other_plan = MarketPlan.objects.create(
        provider=provider_a,
        external_key="provider-a-other",
        first_seen_at=timezone.now(),
        last_seen_at=timezone.now(),
    )
    _snapshot_for_latest_run(provider_a, other_plan, "Otro")
    default = DashboardPreset.objects.create(name="Predeterminado", slug="default-view")
    DashboardPresetProvider.objects.create(preset=default, provider=provider_a)
    settings = DashboardSettings.load()
    settings.default_preset = default
    settings.save()
    explicit = DashboardPreset.objects.create(
        name="Competidor directo",
        slug="direct-competitor",
        plan_selection=DashboardPreset.PlanSelection.EXPLICIT,
    )
    DashboardPresetProvider.objects.create(preset=explicit, provider=provider_a, position=0)
    DashboardPresetProvider.objects.create(preset=explicit, provider=provider_b, position=1)
    DashboardPresetPlan.objects.create(preset=explicit, plan=plan_a, position=0)
    DashboardPresetPlan.objects.create(preset=explicit, plan=plan_b, position=1)

    resolved_default = resolve_dashboard_selection(QueryDict(""))
    resolved_url = resolve_dashboard_selection(QueryDict("preset=direct-competitor"))

    assert resolved_default.preset == default
    assert {plan.id for plan in resolved_default.plans} == {plan_a.id, other_plan.id}
    assert resolved_url.preset == explicit
    assert {plan.id for plan in resolved_url.plans} == {plan_a.id, plan_b.id}


@pytest.mark.django_db
def test_real_url_filters_reject_demo_or_out_of_preset_entities():
    provider, plan, _ = _published_provider("allowed")
    demo_plan = MarketPlan.objects.filter(provider__data_scope=Provider.DataScope.DEMO).first()

    narrowed = resolve_dashboard_selection(
        QueryDict(f"provider={provider.code}&plan={plan.id}&period=3")
    )

    assert narrowed.period_months == 3
    assert narrowed.temporary_filters is True
    with pytest.raises(DashboardSelectionError, match="no pertenecen"):
        resolve_dashboard_selection(QueryDict(f"plan={demo_plan.id}"))
    with pytest.raises(DashboardSelectionError, match="3, 6 o 12"):
        resolve_dashboard_selection(QueryDict("period=24"))


@pytest.mark.django_db
def test_public_resolution_discards_cross_scope_values_and_builds_canonical_url():
    provider, plan, _ = _published_provider("canonical")
    demo_plan = MarketPlan.objects.filter(provider__data_scope=Provider.DataScope.DEMO).first()

    selection = resolve_dashboard_selection(
        QueryDict(
            f"preset=all&period=invalid&provider={provider.code}"
            f"&provider=missing&plan={plan.id}&plan={demo_plan.id}&plan=not-a-number"
        ),
        strict=False,
    )

    assert selection.period_months == 6
    assert selection.providers == (provider,)
    assert selection.plans == (plan,)
    assert selection.temporary_filters is True
    assert len(selection.warnings) == 4
    assert selection.canonical_query == (
        f"preset=all&period=6&provider={provider.code}&plan={plan.id}"
    )


@pytest.mark.django_db
def test_public_resolution_falls_back_when_preset_is_inactive_or_missing():
    inactive = DashboardPreset.objects.create(name="Inactiva", slug="inactive", is_active=False)

    for slug in (inactive.slug, "missing"):
        selection = resolve_dashboard_selection(QueryDict(f"preset={slug}"), strict=False)

        assert selection.preset.slug == DashboardPreset.SYSTEM_ALL_SLUG
        assert selection.warnings == ("La vista solicitada no existe o está inactiva",)
        assert selection.canonical_query == "preset=all&period=6"


@pytest.mark.django_db
def test_switching_real_views_keeps_only_shared_filters_or_restores_target_scope():
    first, first_plan, _ = _published_provider("real-first-view")
    shared, shared_plan, _ = _published_provider("real-shared-view")
    target, target_plan, _ = _published_provider("real-target-view")
    shared_view = DashboardPreset.objects.create(name="Compartida", slug="shared-view")
    target_view = DashboardPreset.objects.create(name="Destino", slug="target-view")
    for position, provider in enumerate((shared, target)):
        DashboardPresetProvider.objects.create(
            preset=shared_view, provider=provider, position=position
        )
    DashboardPresetProvider.objects.create(preset=target_view, provider=target)

    partial = resolve_dashboard_selection(
        QueryDict(
            f"preset=shared-view&provider={first.code}&provider={shared.code}"
            f"&plan={first_plan.id}&plan={shared_plan.id}"
        ),
        strict=False,
    )
    restored = resolve_dashboard_selection(
        QueryDict(f"preset=target-view&provider={first.code}&plan={first_plan.id}"),
        strict=False,
    )

    assert partial.providers == (shared,)
    assert partial.plans == (shared_plan,)
    assert "provider=real-shared-view" in partial.canonical_query
    assert restored.providers == (target,)
    assert restored.plans == (target_plan,)
    assert restored.temporary_filters is False
    assert restored.canonical_query == "preset=target-view&period=6"


@pytest.mark.django_db
def test_dashboard_panels_use_only_published_long_values_and_real_decimal_prices(
    django_assert_num_queries,
):
    provider, plan, provider_run = _published_provider("analytics", price=Decimal("19.90"))
    definition = FeatureDefinition.objects.create(
        code="analytics-feature",
        display_name="Característica analítica",
        data_type="boolean",
        scope="canonical",
        origin="configured",
    )
    snapshot = provider_run.plan_snapshots.get(market_plan=plan)
    PlanFeatureValue.objects.create(
        plan_snapshot=snapshot,
        feature_definition=definition,
        value_boolean=True,
        availability="present",
        origin="rule",
    )
    review = MarketReview.objects.create(
        provider=provider,
        platform_code="maps",
        external_review_id="published-review",
        first_seen_at=timezone.now(),
        last_seen_at=timezone.now(),
    )
    ReviewSnapshot.objects.create(
        market_review=review,
        provider_run=provider_run,
        rating_stars=5,
        ingested_at=timezone.now(),
        review_published_at=timezone.now(),
        sentiment_from_rating="positive",
        content_sha256="a" * 64,
    )
    failed_run = _provider_run(provider, status=PipelineRun.Status.FAILED, days_ago=-1)
    failed_snapshot = PlanSnapshot.objects.create(
        market_plan=plan,
        provider_run=failed_run,
        observed_at=timezone.now(),
        plan_name="No publicado",
    )
    PlanPriceSnapshot.objects.create(
        plan_snapshot=failed_snapshot,
        billing_period="monthly",
        currency_code="USD",
        amount=Decimal("999.99"),
        effective_monthly_amount=Decimal("999.99"),
        source_kind="scraped",
    )
    selection = resolve_dashboard_selection(QueryDict("provider=analytics&period=6"))

    with django_assert_num_queries(8, exact=False):
        data = build_dashboard_data(selection)

    assert data["heatmap"]["rows"][0]["cells"][0]["state"] == "supported"
    assert data["price_rating"]["points"][0]["x"] == 19.9
    assert data["price_rating"]["points"][0]["y"] == 5.0
    assert data["sentiment"]["rows"][0]["positive"] == 100.0
    assert data["plans"][0]["plans"][0]["name"] == "Plan analytics"
    assert data["plans"][0]["plans"][0]["prices"][0]["amount"] == "19.9000"
    assert 999.99 not in data["price_evolution"]["datasets"][0]["values"]


@pytest.mark.django_db
def test_all_aggregates_three_real_providers_without_hiding_partial_panels(
    django_assert_max_num_queries,
):
    Provider.objects.filter(data_scope=Provider.DataScope.REAL).update(is_active=False)
    rows = [
        _published_provider(code, price=Decimal(str(price)))
        for code, price in (("zeta", 30), ("alpha", 10), ("middle", 20))
    ]
    for order, (provider, _plan, _run) in enumerate(rows, start=1):
        provider.execution_order = order
        provider.save(update_fields=("execution_order",))
    definition = FeatureDefinition.objects.create(
        code="multi-provider-feature",
        display_name="Función compartida",
        data_type="boolean",
        scope="canonical",
        origin="configured",
    )
    for provider, plan, provider_run in rows[:2]:
        PlanFeatureValue.objects.create(
            plan_snapshot=provider_run.plan_snapshots.get(market_plan=plan),
            feature_definition=definition,
            value_boolean=True,
            availability="present",
            origin="rule",
        )
        review = MarketReview.objects.create(
            provider=provider,
            platform_code="maps",
            external_review_id=f"{provider.code}-review",
            first_seen_at=timezone.now(),
            last_seen_at=timezone.now(),
        )
        ReviewSnapshot.objects.create(
            market_review=review,
            provider_run=provider_run,
            rating_stars=5,
            ingested_at=timezone.now(),
            review_published_at=timezone.now(),
            sentiment_from_rating="positive",
            content_sha256=provider.code.ljust(64, "0"),
        )

    selection = resolve_dashboard_selection(QueryDict("preset=all&period=6"))
    with django_assert_max_num_queries(8):
        data = build_dashboard_data(selection)

    expected_codes = ["zeta", "alpha", "middle"]
    assert [provider.code for provider in selection.providers] == expected_codes
    assert [item["code"] for item in data["providers"]] == expected_codes
    assert [item["provider"] for item in data["plans"]] == expected_codes
    assert [cell["provider"] for cell in data["heatmap"]["rows"][0]["cells"]] == expected_codes
    assert data["heatmap"]["rows"][0]["cells"][2]["state"] == "unknown"
    assert {item["provider"] for item in data["price_evolution"]["datasets"]} == set(expected_codes)
    assert {item["provider"] for item in data["price_rating"]["points"]} == {
        "zeta",
        "alpha",
    }
    assert [item["provider"] for item in data["sentiment"]["rows"]] == expected_codes
    assert data["sentiment"]["rows"][2]["positive"] is None
    assert [item["color"] for item in data["providers"]] == [
        provider_color_map(tuple(expected_codes))[code] for code in expected_codes
    ]
    colors = {item["code"]: item["color"] for item in data["providers"]}
    assert len(set(colors.values())) == len(expected_codes)
    assert {item["provider"]: item["color"] for item in data["plans"]} == colors
    assert all(
        item["color"] == colors[item["provider"]] for item in data["price_evolution"]["datasets"]
    )
    assert all(item["color"] == colors[item["provider"]] for item in data["price_rating"]["points"])
    assert not any(
        provider.data_scope == Provider.DataScope.DEMO for provider in selection.providers
    )


def test_provider_color_map_resolves_current_and_future_collisions_deterministically():
    current_codes = ("anfibius", "perseo", "siigo_ec", "idrixcontable")
    current = provider_color_map(current_codes)

    assert len(set(current.values())) == len(current_codes)
    assert set(current.values()) <= set(PROVIDER_COLORS)
    assert provider_color_map(tuple(reversed(current_codes))) == current
    current_values = tuple(current.values())
    assert (
        min(
            _oklab_distance(first, second)
            for index, first in enumerate(current_values)
            for second in current_values[index + 1 :]
        )
        > 0.2
    )

    future_codes = tuple(f"provider-{index:02d}" for index in range(24))
    future = provider_color_map(future_codes)
    assert len(future) == 24
    assert len(set(future.values())) == 24
    assert set(PROVIDER_COLORS) <= set(future.values())
    assert any(color not in PROVIDER_COLORS for color in future.values())


def test_provider_color_map_chooses_farthest_okabe_ito_color_at_each_step():
    codes = tuple(f"competitor-{index}" for index in range(len(PROVIDER_COLORS)))
    colors = provider_color_map(codes)
    used: list[str] = []
    remaining = list(PROVIDER_COLORS)

    for code in sorted(codes):
        selected = colors[code]
        if used:
            selected_distance = min(_oklab_distance(selected, color) for color in used)
            maximum_distance = max(
                min(_oklab_distance(candidate, color) for color in used) for candidate in remaining
            )
            assert selected_distance == pytest.approx(maximum_distance)
        used.append(selected)
        remaining.remove(selected)


def _published_provider(
    code: str, *, price: Decimal = Decimal("10.00")
) -> tuple[Provider, MarketPlan, ProviderRun]:
    provider = Provider.objects.create(name=f"Proveedor {code}", code=code)
    plan = MarketPlan.objects.create(
        provider=provider,
        external_key=f"{code}-plan",
        first_seen_at=timezone.now(),
        last_seen_at=timezone.now(),
    )
    provider_run = _provider_run(provider, status=PipelineRun.Status.PUBLISHED)
    snapshot = PlanSnapshot.objects.create(
        market_plan=plan,
        provider_run=provider_run,
        observed_at=timezone.now(),
        plan_name=f"Plan {code}",
    )
    PlanPriceSnapshot.objects.create(
        plan_snapshot=snapshot,
        billing_period="monthly",
        currency_code="USD",
        amount=price,
        effective_monthly_amount=price,
        source_kind="scraped",
    )
    return provider, plan, provider_run


def _provider_run(provider: Provider, *, status: str, days_ago: int = 0) -> ProviderRun:
    profile = PipelineProfile.objects.create(code=f"profile-{uuid4()}", name="Perfil")
    profile_version = PipelineProfileVersion.objects.create(profile=profile, version=1)
    published_at = timezone.now() - timedelta(days=days_ago)
    run = PipelineRun.objects.create(
        profile_version=profile_version,
        trigger_type=PipelineRun.TriggerType.MANUAL,
        status=status,
        started_at=published_at,
        finished_at=published_at,
        published_at=published_at if status == PipelineRun.Status.PUBLISHED else None,
    )
    return ProviderRun.objects.create(
        pipeline_run=run,
        provider=provider,
        sequence=1,
        status=status,
        started_at=published_at,
        finished_at=published_at,
        published_at=published_at if status == PipelineRun.Status.PUBLISHED else None,
        is_complete=status == PipelineRun.Status.PUBLISHED,
    )


def _snapshot_for_latest_run(provider: Provider, plan: MarketPlan, name: str) -> PlanSnapshot:
    provider_run = ProviderRun.objects.filter(
        provider=provider, status=PipelineRun.Status.PUBLISHED
    ).latest("published_at")
    return PlanSnapshot.objects.create(
        market_plan=plan,
        provider_run=provider_run,
        observed_at=timezone.now(),
        plan_name=name,
    )
